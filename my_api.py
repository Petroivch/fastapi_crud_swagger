from fastapi import FastAPI, HTTPException, Depends, APIRouter, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, List
import secrets

app = FastAPI()

# ====== ИМИТАЦИЯ БАЗ ДАННЫХ ======
students = []
current_student_id = 1

# Словари для хранения пользователей и активных сессий (токенов)
users_db = {}   # Формат: {"username": {"username": "...", "password": "...", "role": "..."}}
tokens_db = {}  # Формат: {"token": "username"}

# ====== МОДЕЛИ ДАННЫХ ======
class Student(BaseModel):
    id: Optional[int] = None
    name: str
    course: str
    grade: float

class UserRegister(BaseModel):
    username: str
    password: str
    role: str = "reader"  # Возможные роли: 'reader' (только чтение) или 'admin' (полный доступ)

class Token(BaseModel):
    access_token: str
    token_type: str

# ====== ЗАВИСИМОСТИ (АВТОРИЗАЦИЯ И ПРАВА ДОСТУПА) ======
# Настройка схемы OAuth2. Указываем URL эндпоинта для получения токена.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    """Проверяет валидность токена и возвращает текущего пользователя."""
    username = tokens_db.get(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен или сессия истекла",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return users_db[username]

def require_admin(current_user: dict = Depends(get_current_user)):
    """Проверяет, есть ли у пользователя права администратора."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав. Требуется роль 'admin'."
        )
    return current_user

# ====== МАРШРУТИЗАТОР AUTH ======
auth_router = APIRouter(prefix="/auth", tags=["Auth"])

@auth_router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user: UserRegister):
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")
    
    # Сохраняем пользователя (в реальном проекте пароль нужно хэшировать!)
    users_db[user.username] = user.dict()
    return {"message": f"Пользователь {user.username} успешно зарегистрирован"}

@auth_router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # OAuth2PasswordRequestForm ожидает данные формы (username и password)
    user = users_db.get(form_data.username)
    if not user or user["password"] != form_data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Генерируем уникальный токен
    token = secrets.token_hex(16)
    tokens_db[token] = user["username"]
    
    return {"access_token": token, "token_type": "bearer"}

@auth_router.post("/logout")
def logout(token: str = Depends(oauth2_scheme)):
    if token in tokens_db:
        del tokens_db[token]
        return {"message": "Успешный выход из системы. Токен аннулирован."}
    raise HTTPException(status_code=401, detail="Не авторизован")

# Подключаем роутер к основному приложению
app.include_router(auth_router)

# ====== ЗАЩИЩЕННЫЕ CRUD ЭНДПОИНТЫ ======

# CREATE (Доступно только администраторам)
@app.post("/students", response_model=Student)
def create_student(student: Student, current_user: dict = Depends(require_admin)):
    global current_student_id
    student.id = current_student_id
    current_student_id += 1
    students.append(student)
    return student

# READ (Доступно всем авторизованным пользователям: и reader, и admin)
@app.get("/students", response_model=List[Student])
def get_students(current_user: dict = Depends(get_current_user)):
    return students

@app.get("/students/{student_id}", response_model=Student)
def get_student(student_id: int, current_user: dict = Depends(get_current_user)):
    for s in students:
        if s.id == student_id:
            return s
    raise HTTPException(status_code=404, detail="Студент не найден")

# UPDATE (Доступно только администраторам)
@app.put("/students/{student_id}", response_model=Student)
def update_student(student_id: int, updated: Student, current_user: dict = Depends(require_admin)):
    for i, s in enumerate(students):
        if s.id == student_id:
            updated.id = student_id
            students[i] = updated
            return students[i]
    raise HTTPException(status_code=404, detail="Студент не найден")

# DELETE (Доступно только администраторам)
@app.delete("/students/{student_id}")
def delete_student(student_id: int, current_user: dict = Depends(require_admin)):
    for i, s in enumerate(students):
        if s.id == student_id:
            students.pop(i)
            return {"message": "Студент удален"}
    raise HTTPException(status_code=404, detail="Студент не найден")

print("APP STARTED")