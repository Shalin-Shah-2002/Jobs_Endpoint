"""Base controller providing DI of services via app.state.container."""

from fastapi import Request


class BaseController:
    """Controllers receive their dependencies from a container in app.state.

    This keeps the controllers testable: instantiate them with a fake container.
    """

    def __init__(self, request: Request) -> None:
        self.request = request
        self.container = request.app.state.container
