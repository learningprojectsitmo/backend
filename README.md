[![python](https://badgen.net/badge/python/3.10/blue?icon=python)](https://www.python.org/)
![FastAPI](https://img.shields.io/badge/FastAPI-%23009688?logo=fastapi&logoColor=green&labelColor=006666&color=006666)
![Docker](https://img.shields.io/badge/Docker-%232496ED?logo=docker&logoColor=white)

# Backend of the platform for managing projects

## Description

A web platform for managing collaborative study projects featuring team distribution (auto/manual based on skills and interests), project management (milestones, tasks, roles, progress tracking, notifications), assessment by the teachers, and a public landing site for discovery and onboarding. FastAPI and React are the technological core of the project. The development includes best code practices, such as: clear separation of concerns (API, service, repository layers), testing, logging, and Docker-based deployment. 

Frontend repository of the project is available [here](https://github.com/learningprojectsitmo/frontend).

## Installation 

In order to run the whole project:
1. Install **docker** and **docker-compose**
1. `cd` into the `backend` directory
1. `docker-compose up` will the run the containers: backend, frontend, database

In order to run the backend separately:

1. Install **uv** on your system
2. cd into the backend repository, run `uv sync` - the project dependencies will be installed in a virtual environment
3. `uv run main.py` will run the server, it will be available at *localhost:8000*


## Documentation

main.py boots the FastAPI app: it initializes logging, mounts routers and CORS middleware, and runs the Uvicorn server. Logging setup and router inclusion are handled at startup so middleware, routes, and config are ready before the server accepts requests.

Project structure: src contains API routers, repository base class for async CRUD, a services layer for business logic and permission/formatting responsibilities, and models/schemas for SQLAlchemy and Pydantic. Core holds config, security, dependencies, middleware for requests logging, DB AsyncSession factory, a Unit of Work for transactional consistency, and a container that wires repositories and services for endpoints. Tests live in tests/.

[Full documentation](docs/README.md) of the backend.

## TODO

- The repository should be formatted according to the [LISA's development agreement](https://lisa-itmo.github.io/LISA-Hub/docs/vcs/team_development_agreement.html)
