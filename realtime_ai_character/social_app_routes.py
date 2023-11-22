import datetime
import hashlib
import random
import time

from fastapi.security import APIKeyHeader
from starlette import status
from fastapi import FastAPI, HTTPException, Depends, Security
from sqlalchemy.orm import Session
from starlette.websockets import WebSocket, WebSocketDisconnect

from social_app.user import User, Base, UserInfo, Post, Comment, Like, ChatMessage
from sqlalchemy import create_engine, or_, and_
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel


API_KEY_NAME = 'Authorization'
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Database setup
DATABASE_URL = "sqlite:///./social_app_test.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables (if they don't exist)
Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI()


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def auth_user(db: Session, token: str = None):
    if (token is None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user = db.query(User).filter(User.auth_token == token).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    return user


def get_current_user(db: Session = Depends(get_db), token: str = Security(api_key_header)):
    return auth_user(db, token)


def generate_token(username):
    random_number = random.SystemRandom().randint(1, 1000000)
    token = hashlib.sha256(f"{username}{random_number}".encode()).hexdigest()
    return token


# Pydantic models for request and response
class UserRegisterRequest(BaseModel):
    username: str
    email: str
    password: str


# API route for registration
@app.post("/register/")
def register_user(user_data: UserRegisterRequest, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(User).filter(
        or_(User.email == user_data.email, User.username == user_data.username)
    ).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email or username already registered")

    # Create User and UserInfo objects
    new_user_info = UserInfo()
    new_user = User(username=user_data.username, email=user_data.email, hashed_password=user_data.password, info=new_user_info)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"username": new_user.username, "email": new_user.email}


# Pydantic models for request and response
class UserLoginRequest(BaseModel):
    username: str
    password: str


@app.post("/login/")
def login(user_data: UserRegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user or not user.hashed_password == user_data.password:
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    token = generate_token(user_data.username)
    user.auth_token = token  # Store the token in the user record
    db.add(user)
    db.commit()

    return {"token": token}


@app.get("/user/{user_id}/bio")
def get_user_bio(user_id: int, db: Session = Depends(get_db)):
    user_info = db.query(UserInfo).filter(UserInfo.user_id == user_id).first()
    if user_info:
        return {"bio": user_info.bio}
    else:
        raise HTTPException(status_code=404, detail="User not found")


@app.get("/user/{user_id}/photo")
def get_user_bio(user_id: int, db: Session = Depends(get_db)):
    user_info = db.query(UserInfo).filter(UserInfo.user_id == user_id).first()
    if user_info:
        return {"photo": user_info.photo}
    else:
        raise HTTPException(status_code=404, detail="User not found")


class UserBioUpdateRequest(BaseModel):
    bio: str


@app.put("/user/{user_id}/bio")
def update_user_bio(user_id: int, bio_data: UserBioUpdateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this user's bio")

    user_info = db.query(UserInfo).filter(UserInfo.user_id == user_id).first()
    if user_info:
        user_info.bio = bio_data.bio
        db.commit()
        return {"message": "Bio updated successfully"}
    else:
        raise HTTPException(status_code=404, detail="User not found")


class UserPhotoUpdateRequest(BaseModel):
    photo_url: str  # or use UploadFile type for direct file uploads


@app.put("/user/{user_id}/photo")
def update_user_photo(user_id: int, photo_data: UserPhotoUpdateRequest, db: Session = Depends(get_db)):
    user_info = db.query(UserInfo).filter(UserInfo.user_id == user_id).first()
    if user_info:
        user_info.photo = photo_data.photo_url  # Assuming 'photo' field stores the URL
        db.commit()
        return {"message": "Photo updated successfully"}
    else:
        raise HTTPException(status_code=404, detail="User not found")


@app.post("/users/{user_id}/follow")
def follow_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")

    user_to_follow = db.query(User).filter(User.id == user_id).first()
    if not user_to_follow:
        raise HTTPException(status_code=404, detail="User not found")

    if user_to_follow in current_user.followed:
        raise HTTPException(status_code=400, detail="You are already following this user")

    current_user.followed.append(user_to_follow)
    db.commit()
    return {"message": "User followed successfully"}


@app.post("/users/{user_id}/unfollow")
def unfollow_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_to_unfollow = db.query(User).filter(User.id == user_id).first()
    if not user_to_unfollow:
        raise HTTPException(status_code=404, detail="User not found")

    if user_to_unfollow not in current_user.followed:
        raise HTTPException(status_code=400, detail="You are not following this user")

    current_user.followed.remove(user_to_unfollow)
    db.commit()
    return {"message": "User unfollowed successfully"}


class PostCreateRequest(BaseModel):
    image_url: str
    caption: str


@app.post("/posts/")
def create_post(post_data: PostCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_post = Post(user_id=current_user.id, image_url=post_data.image_url, caption=post_data.caption)
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return new_post


class CommentCreateRequest(BaseModel):
    post_id: int
    content: str


@app.post("/comments/")
def create_comment(comment_data: CommentCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_comment = Comment(post_id=comment_data.post_id, user_id=current_user.id, content=comment_data.content)
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment


@app.post("/likes/")
def like_post(post_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing_like = db.query(Like).filter_by(post_id=post_id, user_id=current_user.id).first()
    if existing_like:
        raise HTTPException(status_code=400, detail="You have already liked this post")

    new_like = Like(post_id=post_id, user_id=current_user.id)
    db.add(new_like)
    db.commit()
    return {"message": "Post liked successfully"}


@app.get("/timeline/{user_id}")
def get_user_timeline(user_id: int, timestamp: int = None, db: Session = Depends(get_db)):
    if timestamp is None:
        timestamp = int(time.time())  # Current Unix timestamp

    datetime_timestamp = datetime.utcfromtimestamp(timestamp)
    posts = (db
             .query(Post)
             .filter(Post.user_id == user_id, Post.created_at < datetime_timestamp)
             .order_by(Post.created_at.desc())
             .limit(20)
             .all())

    if not posts:
        return {"message": "No posts found for this user"}

    # Optionally, you can include more information like comments and likes for each post
    timeline = []
    for post in posts:
        post_data = {
            "post_id": post.id,
            "image_url": post.image_url,
            "caption": post.caption,
            "created_at": post.created_at,
            "post_likes": post.likes
            # Include other fields as needed
        }
        timeline.append(post_data)

    return timeline


@app.get("/timeline")
def get_followers_timeline(timestamp: int = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if timestamp is None:
        timestamp = int(time.time())  # Current Unix timestamp

    # Get the list of users that the current user is following
    following_users = current_user.followed

    # Fetch posts from these users
    datetime_timestamp = datetime.utcfromtimestamp(timestamp)
    posts = (db
             .query(Post)
             .filter(Post.user_id.in_([user.id for user in current_user.followed]), Post.created_at < datetime_timestamp)
             .order_by(Post.created_at.desc())
             .limit(20)
             .all())

    if not posts:
        return {"message": "No posts found in your timeline"}

    # Preparing the timeline data
    timeline = [
        {
            "post_id": post.id,
            "author": post.user.username,
            "image_url": post.image_url,
            "caption": post.caption,
            "created_at": post.created_at,
            "post_likes": post.likes
            # Include other fields as needed
        } for post in posts
    ]

    return timeline


@app.get("/posts/{post_id}/comments")
def get_post_comments(post_id: int, db: Session = Depends(get_db)):
    comments = db.query(Comment).filter(Comment.post_id == post_id).all()
    return comments


@app.get("/posts/{post_id}/likes")
def get_post_likes(post_id: int, db: Session = Depends(get_db)):
    likes = db.query(Like).filter(Like.post_id == post_id).all()
    return likes


class ChatMessageCreateRequest(BaseModel):
    receiver_id: int
    content: str


@app.post("/chat/send")
def send_chat_message(chat_data: ChatMessageCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_message = ChatMessage(sender_id=current_user.id, receiver_id=chat_data.receiver_id, content=chat_data.content)
    db.add(new_message)
    db.commit()
    return {"message": "Chat message sent successfully"}


@app.get("/chat/history/{user_id}")
def get_chat_history(user_id: int, timestamp: int = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if timestamp is None:
        timestamp = int(time.time())

    datetime_timestamp = datetime.utcfromtimestamp(timestamp)
    chat_history = db.query(ChatMessage).filter(
        ChatMessage.timestamp < datetime_timestamp,
        or_(
            and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == user_id),
            and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == current_user.id)
        )
    ).order_by(ChatMessage.timestamp.desc()).limit(20).all()

    return chat_history


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    async with get_db() as db:
        if not token:
            await websocket.close(code=4001)  # Custom close code for 'Authentication Failed'
            return

        user = await auth_user(db, token)  # Synchronously get user, or use run_in_threadpool if necessary
        if user is None:
            await websocket.close(code=4001)  # Custom close code for 'Authentication Failed'
            return

        await websocket.accept()

        try:
            while True:
                # Handle WebSocket communication here
                data = await websocket.receive_text()
                # Process incoming messages...
        except WebSocketDisconnect:
            # Handle disconnection
            pass
