# -*- coding: utf-8 -*-
#
# estimator_configs.py
#

"""
Classification algorithm setup including hyperparameter configurations.

Notes:
* Make sure to update the number of original features in the data set.

"""

__author__ = 'Severin Langberg'
__email__ = 'langberg91@gmail.com'


import numpy as np

from hyperopt.pyll import scope

from backend import hyperparams
from backend.formatting import PipeEstimator

from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.cross_decomposition import PLSRegression


# Globals
CLF_LABEL = 'clf'
# NB WIP: The initial number of features to select from.
NUM_ORIG_FEATURES = 30


@scope.define
def estimator_name_func(param_name):

    global CLF_LABEL

    return '{}__{}'.format(CLF_LABEL, param_name)


classifiers = {
    # Support Vector Machines
    SVC.__name__: {
        'estimator': [
            ('{}_scaler'.format(CLF_LABEL), StandardScaler()),
            (CLF_LABEL, PipeEstimator(SVC()))
        ],
        'params': hyperparams.svc_param_space(
            estimator_name_func,
            # NB: Must select kernel a priori because the hyperparamter space
            # generator function is not evaluated at each suggested
            # configuration. Thus, settings depending on the specified kernel
            # will not be updated according to the sampled kernel function.
            kernel='rbf',
            gamma=None,
            degree=None,
            tol=None,
            C=None,
            shrinking=None,
            coef0=None,
            random_state=None,
            n_features=NUM_ORIG_FEATURES,
            class_weight='balanced',
            max_iter=-1,
            verbose=False,
            cache_size=500
        ),
    },
    # Random Forest Classifier
    RandomForestClassifier.__name__: {
        'estimator': [
            (CLF_LABEL, PipeEstimator(RandomForestClassifier()))
        ],
        'params': hyperparams.trees_param_space(
            estimator_name_func,
            n_estimators=None,
            max_features=None,
            max_depth=None,
            min_samples_split=None,
            min_samples_leaf=None,
            bootstrap=None,
            random_state=None,
            oob_score=False,
            n_jobs=-1,
            verbose=False,
        )
    },
    # Gaussian Naive Bayes.
    GaussianNB.__name__: {
        'estimator': [
            ('{}_scaler'.format(CLF_LABEL), StandardScaler()),
            (CLF_LABEL, PipeEstimator(GaussianNB()))
        ],
        'params': hyperparams.gnb_param_space(
            estimator_name_func, priors=None, var_smoothing=None
        )
    },
    # Logistic Regression
    LogisticRegression.__name__: {
        'estimator': [
            ('{}_scaler'.format(CLF_LABEL), StandardScaler()),
            (CLF_LABEL, PipeEstimator(
                LogisticRegression(
                    solver='liblinear',
                    max_iter=1000,
                    verbose=0,
                    # NOTE: The n_jobs > 1 does not have any effect when solver
                    # is set to 'liblinear'.
                    n_jobs=1,
                    dual=False,
                    multi_class='ovr',
                    warm_start=False,
                    class_weight='balanced',
                )
            ))
        ],
        'params': hyperparams.logreg_hparam_space(
            estimator_name_func,
            # NOTE: Should explicitly specify penalty since this param depends
            # on the selected solver. Using L1 enables dim reduction in high
            # dim classification problems.
            penalty='l1',
            C=None,
            tol=None,
            random_state=None,
            fit_intercept=True,
            intercept_scaling=1,
        )
    },
    # Partial Least Squares Regression
    PLSRegression.__name__: {
        'estimator': [
            ('{}_scaler'.format(CLF_LABEL), StandardScaler()),
            (CLF_LABEL, PipeEstimator(PLSRegression()))
        ],
        'params': hyperparams.plsr_hparam_space(
            estimator_name_func,
            n_components=None,
            tol=None,
            n_features=NUM_ORIG_FEATURES,
            max_iter=-1,
            scale=True,
            copy=True
        )
    }
}
