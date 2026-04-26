# Import all models here so that SQLAlchemy's Base metadata is fully populated
# whenever any model module is used (e.g. in the Celery worker process).
from app.models.user import User  # noqa: F401
from app.models.job import Job  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.topic import Topic  # noqa: F401
from app.models.asset import Asset  # noqa: F401
