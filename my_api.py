from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI()


# ====== МОДЕЛЬ ======
class Student(BaseModel):
    id: int
    name: str
    course: str
    grade: float


students = []
current_id = 1


# ====== CREATE ======
@app.post("/students", response_model=Student)
def create_student(student: Student):
    global current_id
    student.id = current_id
    current_id += 1
    students.append(student)
    return student


# ====== READ ======
@app.get("/students", response_model=List[Student])
def get_students():
    return students


@app.get("/students/{student_id}", response_model=Student)
def get_student(student_id: int):
    for s in students:
        if s.id == student_id:
            return s
    raise HTTPException(status_code=404, detail="Not found")


# ====== UPDATE ======
@app.put("/students/{student_id}", response_model=Student)
def update_student(student_id: int, updated: Student):
    for i, s in enumerate(students):
        if s.id == student_id:
            students[i] = updated
            students[i].id = student_id
            return students[i]
    raise HTTPException(status_code=404, detail="Not found")


# ====== DELETE ======
@app.delete("/students/{student_id}")
def delete_student(student_id: int):
    for i, s in enumerate(students):
        if s.id == student_id:
            students.pop(i)
            return {"message": "Deleted"}
    raise HTTPException(status_code=404, detail="Not found")

print("APP STARTED")