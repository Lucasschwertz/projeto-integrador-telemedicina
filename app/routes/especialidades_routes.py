# app/routes/especialidades_routes.py
import os
from flask import Blueprint, render_template, abort, current_app

especialidade_bp = Blueprint("especialidade", __name__)

@especialidade_bp.route("/especialidade/<nome>")
def especialidade(nome):
    template = f"{nome}.html"
    template_dir = os.path.join(current_app.root_path, "templates", "especialidades")
    caminho = os.path.join(template_dir, template)

    if not os.path.exists(caminho):
        abort(404)

    return render_template(f"especialidades/{template}")
