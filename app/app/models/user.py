import base64
import json
import os
import secrets
import time
from hashlib import md5
from typing import List, Optional

from authlib.jose import jwt
from passlib.apps import custom_app_context as pwd_context
from sqlalchemy import Index
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, Relationship, SQLModel, select

from app.config.config import settings
from app.models import Friend


class User(SQLModel, table=True):
    """
    User
    """

    __tablename__ = "User"
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(default=None, index=True, unique=True)
    email_hash: str
    password_hash: str
    salt: str
    about_me: Optional[str] = Field(default=None)
    origin: int
    email_verified: bool = Field(default=False)
    default_avatar: bool = Field(default=True)
    best_score_single_butterfly: int = Field(default=0)
    best_score_double_butterfly: int = Field(default=0)
    total_flutters: int = Field(default=0)
    total_pipes_cleared: int = Field(default=0)
    total_games: int = Field(default=0)
    achievements: str = Field(default="{}")
    platform: int = Field(default=0)  # 0 = undefined, 1 = web, 2 = IOS/Android, 3 = Both

    tokens: List["UserToken"] = Relationship(back_populates="user")

    friends: List["Friend"] = Relationship(
        back_populates="friend",
        sa_relationship_kwargs={
            "primaryjoin": "User.id==Friend.user_id",
        },
    )
    followers: List["Friend"] = Relationship(
        back_populates="follower",
        sa_relationship_kwargs={
            "primaryjoin": "User.id==Friend.friend_id",
        },
    )

    __table_args__ = (Index("user_index", "email_hash", "origin", unique=True),)

    def hash_password(self, password):
        salt = secrets.token_hex(8)
        self.salt = salt
        self.password_hash = pwd_context.hash(password + salt)

    def verify_password(self, password):
        # If the user has any other origin than regular it should not get here
        # because the verification is does elsewhere. So if it does, we return False
        if self.origin != 0:
            return False
        else:
            return pwd_context.verify(password + self.salt, self.password_hash)

    def befriend(self, user):
        # Only call if the Friend object is not present yet.
        friend = Friend(user_id=self.id, friend_id=user.id, friend_name=user.username)
        return friend

    async def is_friend(self, db: AsyncSession, user):
        if user:
            friend_statement = select(Friend).filter_by(user_id=self.id, friend_id=user.id)
            results = await db.execute(friend_statement)
            friend = results.first()
            if friend:
                return friend.Friend.accepted
            else:
                return False
        else:
            return False

    def generate_auth_token(self, expires_in=1800):
        # also used for email password reset token
        payload = {
            "id": self.id,
            "iss": settings.JWT_ISS,
            "aud": settings.JWT_AUD,
            "sub": settings.JWT_SUB,
            "exp": int(time.time()) + expires_in,  # expiration time
            "iat": int(time.time()),  # issued at
        }
        return jwt.encode(settings.header, payload, settings.jwk)

    def logged_in_web(self):
        # If the user has played on mobile this variable will be 2.
        # Now the user is on web, so we set it to 3. Which is the final state.
        if self.platform == 2:
            self.platform = 3
            return 2
        # If the value is undefined we set the variable to 1, which is web.
        elif self.platform == 0:
            self.platform = 1
            return 1
        return 0

    def logged_in_mobile(self):
        # If the user has played on web this variable will be 1.
        # Now the user is on mobile, so we set it to 3. Which is the final state.
        if self.platform == 1:
            self.platform = 3
            return 2
        # If the value is undefined we set the variable to 2, which is mobile.
        elif self.platform == 0:
            self.platform = 2
            return 1
        return 0

    def check_platform_achieved(self, is_web):
        # we return an int, which indicates what action should be taken.
        # 0 means nothing
        # 1 means update user
        # 2 means platform achievement is achieved
        if self.platform != 3:
            if is_web:
                platform_value = self.logged_in_web()
                if platform_value > 0:
                    return 1
                if platform_value == 2:
                    return 2
            elif not is_web:
                platform_value = self.logged_in_mobile()
                if platform_value > 0:
                    return 1
                if platform_value == 2:
                    return 2
        return 2

    def generate_refresh_token(self, expires_in=345600):
        payload = {
            "user_name": self.username,
            "iss": settings.JWT_ISS,
            "aud": settings.JWT_AUD,
            "sub": settings.JWT_SUB,
            "exp": int(time.time()) + expires_in,  # expiration time
            "iat": int(time.time()),  # issued at
        }
        return jwt.encode(settings.header, payload, settings.jwk)

    def is_verified(self):
        return self.email_verified

    def verify_user(self):
        self.email_verified = True

    def avatar_filename(self):
        return md5(self.email_hash.encode("utf-8")).hexdigest()

    def avatar_filename_small(self):
        return self.avatar_filename() + "_small"

    def avatar_filename_default(self):
        return self.avatar_filename() + "_default"

    def set_new_username(self, new_username):
        self.username = new_username

    def set_default_avatar(self, value):
        self.default_avatar = value

    def is_default(self):
        return self.default_avatar

    def get_user_avatar(self, full=False):
        if self.default_avatar:
            file_name = self.avatar_filename_default()
        else:
            if full:
                file_name = self.avatar_filename()
            else:
                file_name = self.avatar_filename_small()
        file_folder = settings.UPLOAD_FOLDER_AVATARS

        file_path = os.path.join(file_folder, "%s.png" % file_name)
        if not os.path.isfile(file_path):
            return None
        else:
            with open(file_path, "rb") as fd:
                image_as_base64 = base64.encodebytes(fd.read()).decode()
            return image_as_base64

    def get_friend_ids(self):
        return [friend.serialize_minimal for friend in self.friends]

    @property
    def serialize(self):
        # Get detailed user information, mostly used for login
        return {
            "id": self.id,
            "username": self.username,
            "verified": self.email_verified,
            "friends": self.get_friend_ids(),
            "avatar": self.get_user_avatar(True),
            "score": {
                "total_flutters": self.total_flutters,
                "total_pipes_cleared": self.total_pipes_cleared,
                "total_games": self.total_games,
                "best_score_single_butterfly": self.best_score_single_butterfly,
                "best_score_double_butterfly": self.best_score_double_butterfly,
            },
            "achievements": json.loads(self.achievements),
            "origin": self.origin == 0, # we only want to know if it's a regular login
        }

    @property
    def serialize_get(self):
        # get user details without personal information
        return {
            "id": self.id,
            "username": self.username,
            "avatar": self.get_user_avatar(True),
            "score": {
                "total_flutters": self.total_flutters,
                "total_pipes_cleared": self.total_pipes_cleared,
                "total_games": self.total_games,
                "best_score_single_butterfly": self.best_score_single_butterfly,
                "best_score_double_butterfly": self.best_score_double_butterfly,
            },
            "achievements": json.loads(self.achievements),
        }

    @property
    def serialize_minimal(self):
        # get minimal user details
        return {
            "id": self.id,
            "username": self.username,
            "avatar": self.get_user_avatar(False),
        }

    @property
    def serialize_no_detail(self):
        # used after account creation before there is an avatar and when all the scores are 0
        return {
            "id": self.id,
            "username": self.username,
            "score": {
                "total_flutters": 0,
                "total_pipes_cleared": 0,
                "total_games": 0,
                "best_score_single_butterfly": 0,
                "best_score_double_butterfly": 0,
            },
            "achievements": {},
            "origin": self.origin == 0,
        }
