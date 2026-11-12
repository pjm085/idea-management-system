from .routes import features_bp


def register_feature_routes(app):
    app.register_blueprint(features_bp)
