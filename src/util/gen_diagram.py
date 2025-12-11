from sqlalchemy_data_model_visualizer import generate_data_model_diagram, add_web_font_and_interactivity
from model.models import User, Resume, Response, Project, ProjectParticipation
models = [User, Resume, Response, Project, ProjectParticipation]
output_file_name = 'report_diagram'
generate_data_model_diagram(models, output_file_name)
add_web_font_and_interactivity('../db/report_diagram.svg', 'report_diagram.svg')
