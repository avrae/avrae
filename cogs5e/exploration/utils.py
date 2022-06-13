import uuid


def create_explorer_id():
    """Creates a unique string ID for each explorer. Might be changed to ObjectId later."""
    return str(uuid.uuid4())


def create_effect_id():
    """Creates a unique string ID for each effect. Might be changed to ObjectId later."""
    return str(uuid.uuid4())
