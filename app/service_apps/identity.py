from app.app_factory import create_app

app = create_app(router_names=["health", "auth", "admin"])
