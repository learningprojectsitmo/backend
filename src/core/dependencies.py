import jwt
# from dependency_injector.wiring import Provide, inject
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status

from core.config import settings
from core.database import get_db
from core.security import oauth2_scheme
from model.models import User



# @inject
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get('sub')
        if not email:
            print("NO EMAIL")
            raise credentials_exception

    except jwt.PyJWTError:
        print("JWT EXCEPT")
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if not user:
        print("NO USER")
        raise credentials_exception

    return user