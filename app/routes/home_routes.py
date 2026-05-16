from flask import Blueprint, render_template, current_app, send_from_directory

home_bp = Blueprint("home", __name__)

@home_bp.route("/")
def home():
    return render_template("home.html")


@home_bp.route("/sw.js")
def service_worker():
    return send_from_directory(current_app.static_folder, "sw.js")
