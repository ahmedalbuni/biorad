# -*- coding: utf-8 -*-
#
# model_selection.py
#

"""
hyperopt with sklearn
http://steventhornton.ca/hyperparameter-tuning-with-hyperopt-in-python/

Parallelizing Evaluations During Search via MongoDB
https://github.com/hyperopt/hyperopt/wiki/Parallelizing-Evaluations-During-Search-via-MongoDB

Practical notes on SGD: https://scikit-learn.org/stable/modules/sgd.html#tips-on-practical-use

Checkout for plots ++: https://medium.com/district-data-labs/parameter-tuning-with-hyperopt-faa86acdfdce
Checkout: https://github.com/tmadl/highdimensional-decision-boundary-plot
"""

__author__ = 'Severin Langberg'
__email__ = 'langberg91@gmail.com'

import os
import time
import utils
import pickle
import logging

import numpy as np

from scipy import stats
from copy import deepcopy

from datetime import datetime
from collections import OrderedDict

from hyperopt import hp
from hyperopt import tpe
from hyperopt import fmin
from hyperopt import Trials
from hyperopt import space_eval
from hyperopt import STATUS_OK

from hyperopt.pyll.base import scope

from sklearn.base import clone
from sklearn.utils import check_X_y
from sklearn.model_selection import StratifiedKFold


# TODO:
def point_632plus_selection():
    pass


# TODO: Set random states in pipeline estimators.
def bbc_cv_selection(
    X, y,
    algo,
    model_id,
    model,
    param_space,
    score_func,
    cv,
    oob,
    max_evals,
    shuffle,
    verbose=0,
    random_state=None,
    alpha=0.05,
    balancing=True,
    path_tmp_results=None,
    error_score=np.nan,
):
    """
    Work function for parallelizable model selection experiments.

    Args:

        cv (int): The number of folds in stratified k-fold cross-validation.
        oob (int): The number of samples in out-of-bag bootstrap re-sampling.
        max_evals (int): The number of iterations in hyperparameter search.

    """
    if path_tmp_results is not None:
        path_case_file = os.path.join(
            path_tmp_results, 'experiment_{}_{}'.format(
                random_state, model_id
            )
        )
    else:
        path_case_file = ''
    # Determine if results already exists.
    if os.path.isfile(path_case_file):
        output = utils.ioutil.read_prelim_result(path_case_file)
        print('Reloading results from: {}'.format(path_case_file))
    else:
        # Balance target class distributions with SMOTE procedure.
        if balancing:
            X, y = utils.sampling.balance_data(X, y, random_state)

        # Experimental results container.
        output = {'exp_id': random_state}

        if verbose > 0:
            print('Initiating experiment: {}'.format(random_state))
            start_time = datetime.now()

        # TODO: Set random states in pipeline estimators.

        # Perform cross-validated hyperparameter optimization.
        optimizer = ParameterSearchCV(
            algo=algo,
            model=model,
            space=param_space,
            score_func=score_func,
            cv=cv,
            max_evals=max_evals,
            shuffle=shuffle,
            random_state=random_state,
            error_score=error_score,
        )
        # Error handling
        optimizer.fit(X, y)

        # Add available and potentially interesting results to output.
        output.update(optimizer.test_loss)
        output.update(optimizer.train_loss)
        output.update(optimizer.test_loss_var)
        output.update(optimizer.train_loss_var)
        output.update(optimizer.best_params)
        output.update(optimizer.params)

        # Evaluate model performance with BBC-CV method.
        bbc_cv = BootstrapBiasCorrectedCV(
            random_state=random_state,
            score_func=score_func,
            alpha=alpha,
            oob=oob,
        )
        # Returns results directly.
        output.update(bbc_cv.evaluate(*optimizer.oos_pairs))

        if verbose > 0:
            duration = datetime.now() - start_time
            output['exp_duration'] = duration
            print('Experiment {} completed in {}'
                  ''.format(random_state, duration))

        if path_tmp_results is not None:
            utils.ioutil.write_prelim_results(path_case_file, output)

    return output


# TODO: Get GPU speed with TensorFlow.
class BootstrapBiasCorrectedCV:
    """

    Args:
        score_func (function):
        n_iter (int):
        random_state (int):

    """

    def __init__(
        self,
        random_state,
        score_func,
        error_score=np.nan,
        oob=10,
        alpha=0.05,
    ):
        self.random_state = random_state
        self.score_func = score_func
        self.error_score = error_score
        self.oob = oob
        self.alpha = alpha

        self._sampler = None

    # TODO: Get GPU speed with TensorFlow.
    def evaluate(self, Y_pred, Y_true):
        """Bootstrap bias corrected cross-validation proposed by .

        Args:
            Y_pred (array-like): A matrix (N x C) containing out-of-sample
                predictions for N samples and C hyperparameter configurations.
                Thus, scores[i, j] denotes the out-of-sample prediction of on
                the i-th sample of the j-th configuration.
            Y_true ():

        Returns:
            (dict):

        """
        # Generate bootstrapped matrices.
        if self._sampler is None:
            self._sampler = utils.sampling.OOBSampler(
                self.oob, self.random_state
            )
        bbc_scores = []
        # Divide each sampling round (e.g. X500) across TensorFlow GPU backend.
        for sample_idx, oos_idx in self._sampler.split(Y_true, Y_pred):
            best_config = self.criterion(
                Y_true[sample_idx, :], Y_pred[sample_idx, :]
            )
            bbc_scores.append(
                self._score(
                    Y_true[oos_idx, best_config], Y_pred[oos_idx, best_config]
                )
            )
        return {
            'oob_avg_score': np.mean(bbc_scores),
            'oob_std_score': np.std(bbc_scores),
            'oob_median_score': np.median(bbc_scores),
            'oob_score_ci': self.bootstrap_ci(bbc_scores),
        }

    def _score(self, y_true, y_pred):
        # Score function error mechanism.
        try:
            output = self.score_func(y_true, y_pred)
        except:
            output = self.error_score

        return output

    def criterion(self, Y_true, Y_pred):
        """

        Returns:
            (int): Index of the optimal configuration according to the
                score function.

        """
        _, num_configs = np.shape(Y_true)

        losses = np.ones(num_configs, dtype=float) * np.nan
        for num in range(num_configs):
            # Returns <float> or error score (1 - NaN = NaN).
            losses[num] = 1.0 - self._score(Y_true[:, num], Y_pred[:, num])

        # Select the configuration with the minimum loss ignoring NaNs.
        return np.nanargmin(losses)

    def bootstrap_ci(self, scores):
        """Calculate the bootstrap confidence interval from sample data."""

        asc_scores = sorted(scores)

        upper_idx = (1 - self.alpha / 2) * len(scores)
        lower_idx = self.alpha / 2 * len(scores)

        return asc_scores[int(lower_idx)], asc_scores[int(upper_idx)]


# ERROR: Error is raised if attmepting to clone wrapped estimator.
# TODO: Collect ground truths and predictions for BBC-CV procedure.
class ParameterSearchCV:
    """Perform K-fold cross-validated hyperparameter search with the Bayesian
    optimization Tree Parzen Estimator.

    Args:
        model ():
        space ():
        ...

    """

    # NOTE: For pickling results stored in hyperopt Trials() object.
    TEMP_RESULTS_FILE = './tmp_trials.p'

    def __init__(
        self,
        algo,
        model,
        space,
        score_func,
        cv=5,
        max_evals=10,
        shuffle=True,
        random_state=None,
        error_score=np.nan,
    ):
        self.algo = algo
        self.model = model
        self.space = space
        self.shuffle = shuffle
        self.score_func = score_func
        self.error_score = error_score
        self.cv = int(cv)
        self.max_evals = int(max_evals)
        self.random_state = int(random_state)

        # NOTE:
        self.X = None
        self.y = None
        self.trials = None
        # Ground truths and predictions for BBC-CV procedure.
        self._preds = None
        self._grtruths = None
        self._best_params = None

    @property
    def best_params(self):
        """Returns the optimal hyperparameters."""

        return {'model_params': self._best_params}

    @property
    def params(self):

        params = {
            num: res['hparams'] for num, res in enumerate(self.trials.results)
        }
        return {'params': params}

    @property
    def best_model(self):
        """Returns an instance of the estimator with the optimal
        hyperparameters."""

        return self.model.set_params(**self.best_params)

    @property
    def train_loss(self):
        """Returns """

        losses = {
            num: res['train_loss']
            for num, res in enumerate(self.trials.results)
        }
        return {'trainig_loss': losses}

    @property
    def test_loss(self):
        """Returns """

        losses = {
            num: res['loss'] for num, res in enumerate(self.trials.results)
        }
        return {'test_loss': losses}

    @property
    def train_loss_var(self):
        """Returns a dict with the variance of each hyperparameter
        configuration for each K-fold cross-validated training loss."""

        losses = {
            num: res['train_loss_variance']
            for num, res in enumerate(self.trials.results)
        }
        return {'trainig_loss_var': losses}

    @property
    def test_loss_var(self):
        """Returns a dict with the variance of each hyperparameter
        configuration for each K-fold cross-validated test loss."""

        losses = {
            num: res['loss_variance']
            for num, res in enumerate(self.trials.results)
        }
        return {'test_loss_var': losses}

    @property
    def oos_pairs(self):
        """Returns a tuple with ground truths and corresponding out-of-sample
        predictions."""

        preds = np.transpose(
            [items['y_preds'] for items in self.trials.results]
        )
        trues = np.transpose(
            [items['y_trues'] for items in self.trials.results]
        )
        return trues, preds

    def fit(self, X, y):
        """Optimal hyperparameter search.

        Args:
            X (array-like):
            y (array-like):

        """
        self.X, self.y = self._check_X_y(X, y)

        # The Trials object stores information of each iteration.
        if self.trials is None:
            self.trials = Trials()

        # The first n_samples % n_splits folds have size
        # n_samples // n_splits + 1, other folds have size
        # n_samples // n_splits, where n_samples is the number of samples.

        # For saving prelim results: https://github.com/hyperopt/hyperopt/issues/267
        #pickle.dump(optimizer, open(TEMP_RESULTS_FILE, 'wb'))
        #trials = pickle.load(open('TEMP_RESULTS_FILE', 'rb'))

        # Error handling.
        self._best_params = fmin(
            self.objective,
            self.space,
            algo=self.algo,
            max_evals=self.max_evals,
            trials=self.trials,
            rstate=np.random.RandomState(self.random_state)
        )
        return self

    def objective(self, hparams):
        """Objective function to minimize.

        Args:
            hparams (dict): Hyperparameter configuration.

        Returns:
            (dict): Outputs stored in the hyperopt trials object.

        """
        start_time = datetime.now()

        kfolds = StratifiedKFold(self.cv, self.shuffle, self.random_state)

        test_loss, train_loss = [], []
        for train_index, test_index in kfolds.split(self.X, self.y):

            X_train, X_test = self.X[train_index], self.X[test_index]
            y_train, y_test = self.y[train_index], self.y[test_index]

            # Clone model to ensure independency between folds.
            _model = deepcopy(self.model) #clone(self.model)

            # Configure and train model with suggested hyperparamter setting.
            _model.set_params(**hparams)
            _model.fit(X_train, y_train)

            pred_y_test = _model.predict(X_test)
            pred_y_train = _model.predict(X_train)

            print(np.shape(_model.predict(X_test)))

            test_loss.append(1.0 - self.score_func(y_test, pred_y_test))
            train_loss.append(1.0 - self.score_func(y_train, pred_y_train))

            # Collect ground truths and predictions for BBC-CV procedure.
            self._grtruths.append(y_test)
            self._preds.append(pred_y_test)

        """
        return OrderedDict(
            [
                ('status', STATUS_OK),
                ('eval_time', datetime.now() - start_time),
                ('loss', np.median(test_loss)),
                ('train_loss', np.median(train_loss)),
                ('loss_variance', np.var(test_loss)),
                ('train_loss_variance', np.var(train_loss)),
                ('y_trues', _trues,),
                ('y_preds', _preds,),
                ('hparams', hparams)
            ]
        )
        """

    @staticmethod
    def _check_X_y(X, y):
        # A wrapper around sklearn formatter.

        return check_X_y(X, y)


if __name__ == '__main__':

    # TODO: Move to backend?
    import sys
    sys.path.append('./../experiment')

    import os
    import backend
    import model_selection
    import comparison_frame

    from selector_configs import selectors
    from estimator_configs import classifiers

    from hyperopt import tpe

    from sklearn.metrics import roc_auc_score
    from sklearn.metrics import matthews_corrcoef
    from sklearn.metrics import precision_recall_fscore_support

    # TEMP:
    from sklearn.datasets import load_breast_cancer
    from sklearn.preprocessing import StandardScaler

    X, y = load_breast_cancer(return_X_y=True)

    # SETUP:
    CV = 10
    OOB = 500
    MAX_EVALS = 100
    SCORING = roc_auc_score
    #
    pipes_and_params = backend.formatting.pipelines_from_configs(
        selectors, classifiers
    )
    pipe, params = pipes_and_params['PermutationSelection_PLSRegression']

    """

    # TODO: Collect ground truths and predictions for BBC-CV procedure.
    bbc_cv_selection(
        X, y,
        tpe.suggest,
        'PermutationSelection_PLSRegression',
        pipe,
        params,
        SCORING,
        CV,
        OOB,
        MAX_EVALS,
        shuffle=True,
        verbose=0,
        random_state=0,
        alpha=0.05,
        balancing=True,
        error_score=np.nan,
        path_tmp_results=None,
    )
    """
    print(np.shape(X))
    print(np.size(y) / )
