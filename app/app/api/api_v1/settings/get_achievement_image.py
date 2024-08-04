import base64
import os

from app.api.api_v1 import api_router_v1
from app.config.config import settings


@api_router_v1.get("/achievement/image/{image_name}", status_code=200)
async def get_achievement_image(
    image_name: str,
):
    file_folder = settings.ACHIEVEMENT_IMAGES
    file_path = os.path.join(file_folder, "%s.png" % image_name)

    if not os.path.isfile(file_path):
        return {
            "result": False,
            "message": "File not found"
        }
    else:
        with open(file_path, "rb") as fd:
            image_as_base64 = base64.encodebytes(fd.read()).decode()

        return {
            "result": True,
            "achievement_image": image_as_base64
        }
