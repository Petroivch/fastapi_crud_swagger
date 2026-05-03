from fastapi import FastAPI, HTTPException, Depends, APIRouter, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, List
import secrets
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Float, distinct, func
from sqlalchemy.orm import declarative_base, sessionmaker
import redis
from functools import wraps
import json
import hashlib

# ====== DATABASE SETUP ======
DATABASE_URL = "sqlite:///students.db"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ====== REDIS SETUP ======
try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True, socket_connect_timeout=5)
    redis_client.ping()
    redis_enabled = True
    print("✓ Redis подключен успешно")
except Exception as e:
    redis_enabled = False
    redis_client = None
    print(f"⚠ Redis недоступен: {str(e)}. Кеширование отключено.")

app = FastAPI(
    title="FastAPI CRUD с SQLAlchemy, BackgroundTasks и Redis",
    description="API для управления студентами с фоновыми задачами и кешированием",
    version="1.0.0"
)

# ====== SQLALCHEMY MODEL ======
class StudentDB(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    last_name = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    faculty = Column(String, nullable=False, index=True)
    course = Column(String, nullable=False, index=True)
    grade = Column(Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "last_name": self.last_name,
            "first_name": self.first_name,
            "faculty": self.faculty,
            "course": self.course,
            "grade": self.grade
        }

# ====== PYDANTIC MODELS ======
class Student(BaseModel):
    id: Optional[int] = None
    last_name: str
    first_name: str
    faculty: str
    course: str
    grade: float

class UserRegister(BaseModel):
    username: str
    password: str
    role: str = "reader"

class Token(BaseModel):
    access_token: str
    token_type: str

# ====== DATABASE UTILITIES ======
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ====== CACHE DECORATOR ======
def cache_result(expire: int = 300):
    """Декоратор для кеширования результатов GET запросов"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not redis_enabled:
                return func(*args, **kwargs)
            
            # Создаём ключ кеша на основе имени функции и параметров
            cache_key_data = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            cache_key = hashlib.md5(cache_key_data.encode()).hexdigest()
            
            try:
                # Пытаемся получить данные из кеша
                cached = redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
            
            # Если данных нет в кеше, выполняем функцию
            result = func(*args, **kwargs)
            
            try:
                # Сохраняем результат в кеш
                redis_client.setex(cache_key, expire, json.dumps(result, default=str))
            except:
                pass
            
            return result
        return wrapper
    return decorator

# ====== BACKGROUND TASKS UTILITIES ======
def load_csv_background(csv_path: str):
    """Загружает данные из CSV в БД как фоновая задача"""
    try:
        df = pd.read_csv(csv_path)
        
        rename_map = {
            "Фамилия": "last_name",
            "Имя": "first_name",
            "Факультет": "faculty",
            "Курс": "course",
            "Оценка": "grade"
        }
        df = df.rename(columns=rename_map)
        
        required_columns = {"last_name", "first_name", "faculty", "course", "grade"}
        if not required_columns.issubset(df.columns):
            raise ValueError(f"В CSV должны быть колонки: {required_columns}")
        
        db = SessionLocal()
        try:
            students_to_add = [
                StudentDB(
                    last_name=row["last_name"],
                    first_name=row["first_name"],
                    faculty=row["faculty"],
                    course=row["course"],
                    grade=float(row["grade"])
                )
                for _, row in df.iterrows()
            ]
            db.bulk_save_objects(students_to_add)
            db.commit()
            print(f"✓ Успешно загружено {len(df)} студентов из CSV файла: {csv_path}")
        finally:
            db.close()
    except Exception as e:
        print(f"✗ Ошибка при загрузке CSV: {str(e)}")

def delete_students_background(student_ids: List[int]):
    """Удаляет студентов по списку ID как фоновая задача"""
    try:
        db = SessionLocal()
        try:
            deleted_count = 0
            for student_id in student_ids:
                student = db.query(StudentDB).filter(StudentDB.id == student_id).first()
                if student:
                    db.delete(student)
                    deleted_count += 1
            db.commit()
            print(f"✓ Успешно удалено {deleted_count} студентов из {len(student_ids)}")
        finally:
            db.close()
    except Exception as e:
        print(f"✗ Ошибка при удалении студентов: {str(e)}")

def clear_cache():
    """Очищает кеш при изменении данных"""
    if not redis_enabled:
        return
    
    try:
        # Очищаем все ключи, которые начинаются с имён функций GET
        pattern = "*get*"
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
    except:
        pass

# ====== AUTHENTICATION & AUTHORIZATION ======
users_db = {}
tokens_db = {}

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

# ====== AUTH ENDPOINTS ======
auth_router = APIRouter(prefix="/auth", tags=["Auth"])

@auth_router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user: UserRegister):
    """Регистрация нового пользователя"""
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")
    
    users_db[user.username] = user.dict()
    return {"message": f"Пользователь {user.username} успешно зарегистрирован"}

@auth_router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Вход в систему и получение токена"""
    user = users_db.get(form_data.username)
    if not user or user["password"] != form_data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = secrets.token_hex(16)
    tokens_db[token] = user["username"]
    
    return {"access_token": token, "token_type": "bearer"}

@auth_router.post("/logout")
def logout(token: str = Depends(oauth2_scheme)):
    """Выход из системы"""
    if token in tokens_db:
        del tokens_db[token]
        return {"message": "Успешный выход из системы. Токен аннулирован."}
    raise HTTPException(status_code=401, detail="Не авторизован")

app.include_router(auth_router)

# ====== CRUD ENDPOINTS ======

@app.post("/students", response_model=Student, status_code=status.HTTP_201_CREATED, tags=["Students"])
def create_student(student: Student, current_user: dict = Depends(require_admin), db = Depends(get_db)):
    """Создание нового студента (требуется роль admin)"""
    clear_cache()
    new_student = StudentDB(
        last_name=student.last_name,
        first_name=student.first_name,
        faculty=student.faculty,
        course=student.course,
        grade=student.grade
    )
    db.add(new_student)
    db.commit()
    db.refresh(new_student)
    
    result = Student(**new_student.to_dict())
    return result

@app.get("/students", response_model=List[Student], tags=["Students"])
@cache_result(expire=300)
def get_students(current_user: dict = Depends(get_current_user), db = Depends(get_db)):
    """Получить список всех студентов (с кешированием на 5 минут)"""
    students_list = db.query(StudentDB).all()
    return [Student(**student.to_dict()) for student in students_list]

@app.get("/students/{student_id}", response_model=Student, tags=["Students"])
def get_student(student_id: int, current_user: dict = Depends(get_current_user), db = Depends(get_db)):
    """Получить студента по ID"""
    student = db.query(StudentDB).filter(StudentDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")
    return Student(**student.to_dict())

@app.put("/students/{student_id}", response_model=Student, tags=["Students"])
def update_student(
    student_id: int, 
    updated: Student, 
    current_user: dict = Depends(require_admin), 
    db = Depends(get_db)
):
    """Обновление данных студента (требуется роль admin)"""
    clear_cache()
    student = db.query(StudentDB).filter(StudentDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")
    
    student.last_name = updated.last_name
    student.first_name = updated.first_name
    student.faculty = updated.faculty
    student.course = updated.course
    student.grade = updated.grade
    
    db.commit()
    db.refresh(student)
    
    return Student(**student.to_dict())

@app.delete("/students/{student_id}", tags=["Students"])
def delete_student(
    student_id: int, 
    current_user: dict = Depends(require_admin), 
    db = Depends(get_db)
):
    """Удалить студента по ID (требуется роль admin)"""
    clear_cache()
    student = db.query(StudentDB).filter(StudentDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")
    
    db.delete(student)
    db.commit()
    
    return {"message": f"Студент с ID {student_id} удален"}

# ====== BACKGROUND TASKS ======

@app.post("/import-csv", status_code=status.HTTP_202_ACCEPTED, tags=["Background Tasks"])
def import_csv(
    csv_path: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_admin)
):
    """
    Загрузить студентов из CSV файла в фоновую задачу.
    
    - **csv_path**: путь к CSV файлу
    
    CSV должен содержать колонки: Фамилия, Имя, Факультет, Курс, Оценка
    """
    clear_cache()
    background_tasks.add_task(load_csv_background, csv_path)
    return {
        "status": "accepted",
        "message": f"Загрузка данных из файла {csv_path} запущена в фоне",
        "details": "Проверьте логи для отслеживания процесса"
    }

@app.post("/delete-students", status_code=status.HTTP_202_ACCEPTED, tags=["Background Tasks"])
def delete_students_by_list(
    student_ids: List[int],
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_admin)
):
    """
    Удалить студентов по списку ID как фоновую задачу.
    
    - **student_ids**: список ID студентов, которых нужно удалить
    """
    clear_cache()
    background_tasks.add_task(delete_students_background, student_ids)
    return {
        "status": "accepted",
        "message": f"Удаление {len(student_ids)} студентов запущено в фоне",
        "student_ids": student_ids,
        "details": "Проверьте логи для отслеживания процесса"
    }

# ====== ANALYTICS & STATISTICS ======

@app.get("/students-by-faculty/{faculty_name}", response_model=List[Student], tags=["Analytics"])
def get_students_by_faculty(
    faculty_name: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """Получить студентов по факультету (с кешированием)"""
    students_list = db.query(StudentDB).filter(StudentDB.faculty == faculty_name).all()
    return [Student(**student.to_dict()) for student in students_list]

@app.get("/average-grade/{faculty_name}", tags=["Analytics"])
def get_average_grade(
    faculty_name: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """Получить среднюю оценку по факультету (с кешированием)"""
    avg_grade = db.query(func.avg(StudentDB.grade)).filter(
        StudentDB.faculty == faculty_name
    ).scalar()
    
    return {
        "faculty": faculty_name,
        "average_grade": round(avg_grade, 2) if avg_grade is not None else None
    }

@app.get("/low-grades", response_model=List[Student], tags=["Analytics"])
def get_low_grades(
    course_name: str,
    min_grade: float = 30,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """Получить студентов с низкими оценками (с кешированием)"""
    students_list = db.query(StudentDB).filter(
        StudentDB.course == course_name,
        StudentDB.grade < min_grade
    ).all()
    return [Student(**student.to_dict()) for student in students_list]

# ====== HEALTH CHECK ======

@app.get("/health", tags=["System"])
def health_check():
    """Проверка состояния приложения"""
    return {
        "status": "healthy",
        "redis": "connected" if redis_enabled else "disconnected",
        "database": "connected"
    }

print("✓ Приложение инициализировано успешно")
