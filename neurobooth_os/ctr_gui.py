from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.templating import Jinja2Templates

import neurobooth_os.iout.metadator as meta

templates = Jinja2Templates(directory="templates")
task_list = ["calibration_obs_1", "saccades_horizontal_obs_1", "timing_test_obs", "clapping_test_obs"]


async def json(request: Request):
    return JSONResponse(content={"Hello": "World"})


async def page_1(request: Request):
    studies = meta.get_study_ids()
    studies.insert(0, "Select a study")
    return templates.TemplateResponse("page_1.html", {'request': request, 'name': 'larry', 'studies': studies})


async def page_2(request: Request):
    return templates.TemplateResponse("page_2.html", {'request': request, 'name': 'larry', 'tasks': task_list})

routes = [Route('/page_1', endpoint=page_1),
          Route('/json', endpoint=json),
          Route('/page_2', endpoint=page_2)]


app = Starlette(
    debug=True,
    routes=routes
)