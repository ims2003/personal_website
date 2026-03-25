from flask import Blueprint, render_template

home = Blueprint('home', __name__, template_folder='templates')

@home.route("/")
def index():
    return render_template("home.html")

@home.route("/about")
def about():
    return render_template("about.html")

@home.route("/resume")
def resume():
    return render_template("resume.html")

@home.route("/projects")
def projects():
    return render_template("projects.html")

@home.route("/pursuits")
def pursuits():
    return render_template("pursuits.html")


