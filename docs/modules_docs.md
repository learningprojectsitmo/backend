# main.py

`main.py` is the main entry point for the application. 
The following actions are performed:

1. Initialize the FastAPI app 
1. Initialize logging at startup
1. Include the router 
1. Include the CORS middleware 
1. Run uvicorn server

# src

The code for the project 

## API

API routers live here. A router groups related endpoint functions using a decorator.
Each router usually corresponds to one entity and its endpoints are usually placed in a module with the same name.
For example, the `project_router` lives in `api.v1.endpoints.project` module. 

Each API version resides in its own directory (for example: `api/v1/`).
All the routers are merged into one versioned router object in the `routes.py` file for convenient import in `main.py`.

## repository/base_repository.py

A reusable base repository protocol for async database access.

It provides a common set of CRUD operations so you don't repeat the same data-access code across entity repositories.

Concrete repositories inherit from or implement this protocol to get standard methods (create, get, list, update, delete). Keep entity-specific queries in the concrete repository for each model.
base class

## services

The services layer is needed for the business logic, whereas the repositories are only for database access. 
Some of the services functions:
- Converting repository output and errors to domain errors 
- Producing formatted outputs (e.g. paginated lists).
- Enforce permissions

Similarly to repositories, there is a base class, that helps avoid rewriting the same services which are just wrappers over the corresponding repositories.

## model/models.py

All the SQLAlchemy are now models in one module.
TODO: consider splitting models into seperate modules.  

## schema

Pydantic schemas organized in modules by entity.

## core

### exceptions.py

Custom exception classes. 
All exceptions are logged.

### logging_config.py

Logging functions (process the logging event) and some of the logging configuration. TODO: consider moving logging configuration to `config.py` and renaming the module

### config.py

Module for the main settings class. The following settings are included:
- Allowed addresses for CORS 
- Detalais for the database connection
- Logging
- JWT settings 

### security.py

`oauth2_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/token")`

OAuth2PasswordBearer extracts tokens from client requests and returns raw token strings. The tokenUrl is passed solely for the OpenAPI docs and the UX (FastAPI automatically tells the client which endpoind to call to obtain the token).

### dependencies.py

Functions that are called with `= Depends(denpendency_name)` from endpoint functions. They allow to get information about the requesting user based on the provided token. For example, role checking will be implemented here. The dependency functions themselves are dependent on the `oauth2_scheme` for token obtainance.

### middleware/logging_middleware.py

FastAPI middleware that logs incoming HTTP requests, their outcomes, and processing time, and optionally excludes some paths (docs, health, etc.). It also adds an X-Process-Time response header and tries to get the client IP from common headers. The middleware is run at every request.

### database.py

Create and configure a callable `AsyncSessionLocal`, which will be used to create async sessions on demand. Also some configuration of the database connection is performed. 

### uow.py

The Unit Of Work pattern allows to implement transactions logic at the application level (not at the database level).
If an error occurs, all the changes rollback to the initial state. Otherwise, they are committed to the database.

### container.py

Merges the repositories layer and the services layer, wraps them into one `get_some_service` function, which will be called from the endpoint function to get the services.

# tests

TODO: consider moving tests directory to src/ 
