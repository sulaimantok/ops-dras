from flask import Blueprint, render_template

from app import db
from app.auth_utils import login_required

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@login_required
def index():
    return render_template("dashboard.html", stats=db.dashboard_stats(), recent_tasks=db.list_tasks(limit=8))
