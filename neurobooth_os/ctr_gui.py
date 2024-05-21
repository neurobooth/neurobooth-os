from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.templating import Jinja2Templates

import neurobooth_os.iout.metadator as meta

templates = Jinja2Templates(directory="templates")
task_list = ["calibration_obs_1", "saccades_horizontal_obs_1", "timing_test_obs", "clapping_test_obs"]


async def page_1(request: Request):
    study_ids = meta.get_study_ids()
    studies = meta.read_studies()
    collections = meta.read_collections()
    study_ids.insert(0, "Select a study")
    return templates.TemplateResponse("page_1.html", {'request': request,
                                                      'name': 'larry',
                                                      'study_ids': study_ids,
                                                      'studies': studies,
                                                      'collections': collections})


async def page_2(request: Request):
    return templates.TemplateResponse("page_2.html", {'request': request, 'name': 'larry', 'tasks': task_list})

routes = [Route('/page_1', endpoint=page_1),
          Route('/page_2', endpoint=page_2)]


app = Starlette(
    debug=True,
    routes=routes
)


