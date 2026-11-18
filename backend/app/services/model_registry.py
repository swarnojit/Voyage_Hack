"""SQL persistence for synthetic model evaluations and approved scan predictions."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import ModelSnapshot, ModelPrediction
from .ml_planner import train_models


def ensure_model_snapshot(db: Session):
    metadata = train_models()[2]
    version = metadata['model_version']
    item = db.scalar(select(ModelSnapshot).where(ModelSnapshot.model_version == version))
    if item is None:
        item = ModelSnapshot(model_version=version, training_source=metadata['training_source'], metrics=metadata)
        db.add(item)
        db.flush()
    return item


def save_prediction(db: Session, prediction: dict, actor: str, case: str, scan_id: int | None = None):
    ensure_model_snapshot(db)
    item = ModelPrediction(scan_id=scan_id, actor=actor, case=case,
                           model_version=prediction['model_version'],
                           feature_vector=prediction['feature_vector'],
                           risk_score=prediction['risk_priority_score'],
                           novelty_score=prediction['novelty_score'],
                           predicted_class=prediction['predicted_class'],
                           class_confidence=prediction['class_confidence'],
                           explanation={'priority_band': prediction['priority_band'],
                                        'top_risk_drivers': prediction['top_risk_drivers'],
                                        'class_distribution': prediction['class_distribution'],
                                        'novelty_outlier': prediction['novelty_outlier'],
                                        'disclaimer': prediction['explanation']})
    db.add(item)
    db.flush()
    return item
