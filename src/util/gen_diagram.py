from sqlalchemy_data_model_visualizer import add_web_font_and_interactivity, generate_data_model_diagram

from model.models import Project, ProjectParticipation, Response, Resume, User

models = [User, Resume, Response, Project, ProjectParticipation]
output_file_name = 'report_diagram'
generate_data_model_diagram(models, output_file_name)
add_web_font_and_interactivity('../db/report_diagram.svg', 'report_diagram.svg')
