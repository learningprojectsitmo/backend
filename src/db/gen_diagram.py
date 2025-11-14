from sqlalchemy_data_model_visualizer import generate_data_model_diagram, add_web_font_and_interactivity
from models import User, Resume, Response, Project
models = [User, Resume, Response, Project]
output_file_name = 'first_try'
generate_data_model_diagram(models, output_file_name)
add_web_font_and_interactivity('first_try.svg', 'first_try.svg')
