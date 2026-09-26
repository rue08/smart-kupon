from pathlib import Path

from django.http import FileResponse, HttpResponse

OPENAPI_SPEC_PATH = Path(__file__).resolve().parent.parent / 'openapi.yaml'

SCALAR_PAGE = """<!doctype html>
<html>
  <head>
    <title>SmartKupon API Reference</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
  </head>
  <body>
    <script id="api-reference" data-url="/openapi.yaml"></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
  </body>
</html>
"""


def api_docs(request):
    return HttpResponse(SCALAR_PAGE)


def openapi_spec(request):
    return FileResponse(open(OPENAPI_SPEC_PATH, 'rb'), content_type='application/yaml')
