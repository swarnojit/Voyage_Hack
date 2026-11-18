"""Fully local, reproducible synthetic ML test planning laboratory.

Three sklearn models:
  1. RandomForest risk-ranking (trained on simulated endpoint telemetry).
  2. TF-IDF + multinomial logistic threat classification (template-split evaluation).
  3. IsolationForest unfamiliar endpoint-change anomaly estimation.

NEVER use predictions as verification, unsafe payload authorisation, or security truth.
The actual security oracle remains an independent fixed-rule implementation.
"""
from __future__ import annotations
from functools import lru_cache
from hashlib import sha256
import json
import math
import numpy as np
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, brier_score_loss, classification_report,
                             confusion_matrix, f1_score, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

FEATURE_NAMES = [
    'authorization_boundary', 'financial_mutation', 'legacy_endpoint',
    'undocumented_endpoint', 'privileged_operation', 'cross_role_flow',
    'write_method', 'recently_changed',
]
FEATURE_HELP = {
    'authorization_boundary': 'Cross-user or cross-agency object ownership is involved',
    'financial_mutation': 'The request can change payment or refund records',
    'legacy_endpoint': 'This is an old or deprecated API version',
    'undocumented_endpoint': 'Route is missing from the approved API registry',
    'privileged_operation': 'The operation needs elevated permissions',
    'cross_role_flow': 'The journey changes users, agencies, or roles',
    'write_method': 'API changes state rather than only reading it',
    'recently_changed': 'Endpoint appeared in a recent synthetic deployment',
}
CASE_DESCRIPTIONS = {
    'cross_agency': 'Booking access control: one travel agency reads another agency private hotel booking by object identifier.',
    'double_refund': 'Payments business logic: repeated POST refund command may return more money than the original booking charge.',
    'legacy_bypass': 'Old undocumented legacy v1 booking endpoint may bypass agency authorization and expose another agency data.',
}
CASE_FEATURES = {
    'cross_agency': [1, 0, 0, 0, 0, 1, 0, 1],
    'double_refund': [0, 1, 0, 0, 1, 0, 1, 1],
    'legacy_bypass': [1, 0, 1, 1, 0, 1, 0, 1],
}
SEED = 20261118
THREAT_PHRASES = {
    'authorization': [
        'foreign agency booking visibility', 'cross tenant property lookup',
        'horizontal booking authorization', 'private traveler itinerary access',
        'object identifier ownership check', 'access denied across agent roles',
        'agency boundary permission change', 'customer record scope bypass',
        'foreign invoice reading', 'role scoping for booking GET',
    ],
    'financial_logic': [
        'duplicate refund replay', 'double credit transaction',
        'financial conservation invariant', 'refund idempotency request',
        'cancel rebook refund amount', 'payment ledger double spend',
        'payment amount authorization', 'cumulative refund exceeds charge',
        'repeated money return request', 'cancel order refund state',
    ],
    'legacy_api': [
        'retired version endpoint', 'zombie application route',
        'legacy gateway security bypass', 'old undocumented integration',
        'deprecated supplier api', 'historical javascript route',
        'obsolete api handler discovered', 'v1 legacy service exposure',
        'stale route deprecated', 'unmaintained old booking API',
    ],
}
PREFIXES = ['travel api', 'synthetic release', 'booking change', 'staging route']
MODEL_VERSION = sha256(json.dumps({
    'seed': SEED, 'features': FEATURE_NAMES, 'threat_phrases': THREAT_PHRASES,
    'algorithm': 'RF-120-IForest-TFIDF-LR-v3'}, sort_keys=True).encode()).hexdigest()[:16]


def _risk_dataset():
    rng = np.random.default_rng(SEED)
    x = rng.integers(0, 2, size=(1800, len(FEATURE_NAMES)), dtype=np.int32)
    logits = (1.65*x[:, 0]+1.65*x[:, 1]+0.98*x[:, 2]+.64*x[:, 3]
              +.58*x[:, 4]+.46*x[:, 5]+.31*x[:, 6]+.79*x[:, 7]
              +0.38*x[:, 0]*x[:, 5]+rng.normal(0, .99, len(x)))
    y = (logits > 3.1).astype(np.int32)
    return x, y


def _threat_dataset():
    # Split source PHRASES before expanding prefixes, to avoid template leakage.
    train_text, train_label, test_text, test_label = [], [], [], []
    for label, phrases in THREAT_PHRASES.items():
        rng = np.random.default_rng(SEED + len(label))
        order = rng.permutation(len(phrases))
        training_set = {int(i) for i in order[:8]}
        for i, phrase in enumerate(phrases):
            # New phrasing held out by phrase family, not by shared prefix.
            for prefix in PREFIXES:
                if i in training_set:
                    train_text.append(prefix + ' ' + phrase); train_label.append(label)
                else:
                    test_text.append(prefix + ' ' + phrase); test_label.append(label)
    return train_text, train_label, test_text, test_label


@lru_cache(maxsize=1)
def train_models():
    x, y = _risk_dataset()
    xa, xb, ya, yb = train_test_split(x, y, test_size=.25, random_state=42, stratify=y)
    risk = RandomForestClassifier(n_estimators=120, max_depth=7, min_samples_leaf=5,
                                  class_weight='balanced_subsample', random_state=42, n_jobs=1)
    risk.fit(xa, ya)
    risk_prob = risk.predict_proba(xb)[:, 1]
    risk_labels = (risk_prob >= .5).astype(int)
    train_txt, train_lab, test_txt, test_lab = _threat_dataset()
    classifier = Pipeline([
        ('vectorizer', TfidfVectorizer(ngram_range=(1, 2), stop_words='english', sublinear_tf=True)),
        ('classifier', LogisticRegression(max_iter=1500, random_state=42)),
    ])
    classifier.fit(train_txt, train_lab)
    predicted = classifier.predict(test_txt)
    risk_report = {
        'accuracy': round(float(accuracy_score(yb, risk_labels)), 4),
        'precision': round(float(precision_score(yb, risk_labels, zero_division=0)), 4),
        'recall': round(float(recall_score(yb, risk_labels, zero_division=0)), 4),
        'f1': round(float(f1_score(yb, risk_labels, zero_division=0)), 4),
        'roc_auc': round(float(roc_auc_score(yb, risk_prob)), 4),
        'brier': round(float(brier_score_loss(yb, risk_prob)), 4),
        'confusion_matrix': confusion_matrix(yb, risk_labels).tolist(),
    }
    class_report = classification_report(test_lab, predicted, output_dict=True, zero_division=0)
    intent_report = {
        'accuracy': round(float(accuracy_score(test_lab, predicted)), 4),
        'macro_f1': round(float(f1_score(test_lab, predicted, average='macro', zero_division=0)), 4),
        'per_class': {label: {'precision': round(float(class_report[label]['precision']), 4),
                              'recall': round(float(class_report[label]['recall']), 4),
                              'f1': round(float(class_report[label]['f1-score']), 4)}
                      for label in THREAT_PHRASES},
        'test_phrases_held_out': 2 * len(THREAT_PHRASES),
    }
    metadata = {
        'model_version': MODEL_VERSION,
        'risk_model': 'RandomForestClassifier (120 trees, depth 7)',
        'intent_model': 'TfidfVectorizer + LogisticRegression',
        'anomaly_model': 'IsolationForest (normal-operation synthetic telemetry)',
        'samples': int(len(x)),
        'risk_train_rows': int(len(xa)), 'risk_holdout_rows': int(len(xb)),
        'intent_train_rows': len(train_txt), 'intent_holdout_rows': len(test_txt),
        'risk_holdout_accuracy_synthetic': risk_report['accuracy'],
        'risk_metrics': risk_report, 'intent_metrics': intent_report,
        'training_source': 'GENERATED SYNTHETIC EXAMPLES ONLY',
        'dataset_split': '25% stratified risk holdout; threat classification phrase families held out',
        'external_inference': False, 'model_artifacts_loaded': False,
        'risk_feature_names': FEATURE_NAMES,
        'feature_descriptions': FEATURE_HELP,
        'feature_importance': {FEATURE_NAMES[i]: round(float(importance), 4)
                               for i, importance in enumerate(risk.feature_importances_)},
        'execution_policy': 'ML ranks preapproved tests; deterministic replay proves findings',
        'limitations': 'Synthetic data does not validate detection on unseen real TBO vulnerabilities.',
    }
    return risk, classifier, metadata


@lru_cache(maxsize=1)
def _anomaly_model():
    x, y = _risk_dataset()
    normal = x[y == 0]
    model = IsolationForest(n_estimators=100, contamination=.07, random_state=2026, n_jobs=1)
    model.fit(normal)
    return model


def predict_features(features: list[int], description: str) -> dict:
    if len(features) != len(FEATURE_NAMES) or any(v not in (0, 1) for v in features):
        raise ValueError('Exactly 8 binary endpoint indicators are required')
    if not description or len(description) > 280:
        raise ValueError('Synthetic endpoint description must be 1–280 characters')
    risk, classifier, metadata = train_models()
    anomaly = _anomaly_model()
    risk_score = float(risk.predict_proba([features])[0, 1])
    probs = classifier.predict_proba([description])[0]
    rank = np.argsort(probs)[::-1]
    cls = str(classifier.classes_[rank[0]])
    baseline = list(features)
    drivers = []
    for i, present in enumerate(features):
        if not present: continue
        other = list(baseline); other[i] = 0
        delta = risk_score - float(risk.predict_proba([other])[0, 1])
        drivers.append({'feature': FEATURE_NAMES[i], 'effect_if_removed': round(delta, 4),
                        'label': FEATURE_HELP[FEATURE_NAMES[i]]})
    drivers.sort(key=lambda v: abs(v['effect_if_removed']), reverse=True)
    margin = float(anomaly.decision_function([features])[0])
    novelty = float(1.0 / (1.0 + math.exp(max(-60, min(60, margin * 16)))))
    band = 'high' if risk_score >= .75 else 'elevated' if risk_score >= .45 else 'routine'
    return {
        'model_version': metadata['model_version'],
        'risk_priority_score': round(risk_score, 4),
        'priority_band': band,
        'predicted_class': cls,
        'class_confidence': round(float(probs[rank[0]]), 4),
        'class_distribution': {str(classifier.classes_[i]): round(float(probs[i]), 4)
                               for i in range(len(probs))},
        'novelty_score': round(novelty, 4), 'novelty_outlier': bool(margin < 0),
        'anomaly_margin': round(margin, 4),
        'top_risk_drivers': drivers[:5],
        'feature_vector': dict(zip(FEATURE_NAMES, features)),
        'explanation': ('Model scores only prioritize or flag approved tests. '
                        'A deterministic business-rule oracle verifies every finding.'),
    }


def predict_case(kind: str) -> dict:
    if kind not in CASE_DESCRIPTIONS:
        raise ValueError('Unregistered security test')
    pred = predict_features(CASE_FEATURES[kind], CASE_DESCRIPTIONS[kind])
    pred.update({'case': kind, 'model': 'RandomForest + TF-IDF/LogReg + IsolationForest',
                 'reason': 'Risk and novelty models rank fixed tests only; never generate exploit instructions'})
    return pred


def prioritize(cases: list[str]) -> list[dict]:
    return sorted([predict_case(k) for k in cases],
                  key=lambda p: (p['risk_priority_score'], p['novelty_score']), reverse=True)
