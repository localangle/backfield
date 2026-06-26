from backfield_auth.health_router import create_health_router

router = create_health_router("stylebook-api", include_redis=True)
