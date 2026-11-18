from fastapi.encoders import jsonable_encoder


def obj(row, *keys):
    return jsonable_encoder({k: getattr(row, k) for k in keys})
