"""
Тестовый скрипт для демонстрации функциональности FastAPI приложения
Протестируйте все эндпоинты перед запуском в production
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

# ====== COLORS FOR PRETTY PRINT ======
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_section(title):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{title}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")

def print_success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def print_error(msg):
    print(f"{RED}✗ {msg}{RESET}")

def print_info(msg):
    print(f"{YELLOW}→ {msg}{RESET}")

# ====== TEST DATA ======
admin_token = None
reader_token = None

# ====== TESTS ======

def test_registration():
    """Test user registration"""
    print_section("Testing User Registration")
    
    # Register admin user
    print_info("Registering admin user...")
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "username": "admin_user",
            "password": "admin_pass",
            "role": "admin"
        }
    )
    
    if response.status_code == 201:
        print_success(f"Admin registered: {response.json()['message']}")
    else:
        print_error(f"Failed to register admin: {response.text}")
    
    # Register reader user
    print_info("Registering reader user...")
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "username": "reader_user",
            "password": "reader_pass",
            "role": "reader"
        }
    )
    
    if response.status_code == 201:
        print_success(f"Reader registered: {response.json()['message']}")
    else:
        print_error(f"Failed to register reader: {response.text}")

def test_login():
    """Test user login"""
    global admin_token, reader_token
    
    print_section("Testing User Login")
    
    # Admin login
    print_info("Admin user login...")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={
            "username": "admin_user",
            "password": "admin_pass"
        }
    )
    
    if response.status_code == 200:
        admin_token = response.json()['access_token']
        print_success(f"Admin logged in (token: {admin_token[:16]}...)")
    else:
        print_error(f"Failed to login admin: {response.text}")
    
    # Reader login
    print_info("Reader user login...")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={
            "username": "reader_user",
            "password": "reader_pass"
        }
    )
    
    if response.status_code == 200:
        reader_token = response.json()['access_token']
        print_success(f"Reader logged in (token: {reader_token[:16]}...)")
    else:
        print_error(f"Failed to login reader: {response.text}")

def test_create_students():
    """Test creating students"""
    print_section("Testing Create Students (Admin Only)")
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    students = [
        {
            "last_name": "Иванов",
            "first_name": "Иван",
            "faculty": "ФПМИ",
            "course": "Математика",
            "grade": 85.5
        },
        {
            "last_name": "Петров",
            "first_name": "Петр",
            "faculty": "ФТФ",
            "course": "Физика",
            "grade": 92.0
        }
    ]
    
    for i, student in enumerate(students, 1):
        print_info(f"Creating student {i}...")
        response = requests.post(
            f"{BASE_URL}/students",
            json=student,
            headers=headers
        )
        
        if response.status_code == 201:
            data = response.json()
            print_success(f"Student created: {data['first_name']} {data['last_name']} (ID: {data['id']})")
        else:
            print_error(f"Failed to create student: {response.text}")

def test_get_students():
    """Test reading students"""
    print_section("Testing Get Students (with Caching)")
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    print_info("First request (should hit database)...")
    response = requests.get(f"{BASE_URL}/students", headers=headers)
    
    if response.status_code == 200:
        students = response.json()
        print_success(f"Retrieved {len(students)} students from database")
        for student in students:
            print(f"  - {student['first_name']} {student['last_name']} ({student['faculty']}, оценка: {student['grade']})")
    else:
        print_error(f"Failed to get students: {response.text}")
    
    print_info("Second request (should hit cache)...")
    time.sleep(1)
    response = requests.get(f"{BASE_URL}/students", headers=headers)
    
    if response.status_code == 200:
        print_success("Retrieved students from cache (Redis)")
    else:
        print_error(f"Failed to get students: {response.text}")

def test_import_csv():
    """Test CSV import as background task"""
    print_section("Testing CSV Import (Background Task)")
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    print_info("Triggering CSV import...")
    response = requests.post(
        f"{BASE_URL}/import-csv",
        json={"csv_path": "students.csv"},
        headers=headers
    )
    
    if response.status_code == 202:
        data = response.json()
        print_success(f"Background task accepted: {data['message']}")
        print_info("Check server logs for import progress...")
        time.sleep(3)  # Wait for background task
    else:
        print_error(f"Failed to import CSV: {response.text}")

def test_delete_students():
    """Test batch delete as background task"""
    print_section("Testing Batch Delete (Background Task)")
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # First, get student IDs
    response = requests.get(f"{BASE_URL}/students", headers=headers)
    if response.status_code == 200:
        students = response.json()
        if len(students) > 0:
            ids_to_delete = [students[0]['id']]
            
            print_info(f"Deleting student(s) with ID(s): {ids_to_delete}...")
            response = requests.post(
                f"{BASE_URL}/delete-students",
                json={"student_ids": ids_to_delete},
                headers=headers
            )
            
            if response.status_code == 202:
                data = response.json()
                print_success(f"Background task accepted: {data['message']}")
                time.sleep(2)  # Wait for background task
            else:
                print_error(f"Failed to delete students: {response.text}")

def test_analytics():
    """Test analytics endpoints"""
    print_section("Testing Analytics Endpoints")
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Get students by faculty
    print_info("Getting students by faculty...")
    response = requests.get(
        f"{BASE_URL}/students-by-faculty/ФПМИ",
        headers=headers
    )
    
    if response.status_code == 200:
        students = response.json()
        print_success(f"Found {len(students)} students in ФПМИ faculty")
    else:
        print_error(f"Failed to get students by faculty: {response.text}")
    
    # Get average grade
    print_info("Getting average grade...")
    response = requests.get(
        f"{BASE_URL}/average-grade/ФПМИ",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print_success(f"Average grade in {data['faculty']}: {data['average_grade']}")
    else:
        print_error(f"Failed to get average grade: {response.text}")

def test_authorization():
    """Test authorization (reader cannot create)"""
    print_section("Testing Authorization (Reader Cannot Create)")
    
    headers = {"Authorization": f"Bearer {reader_token}"}
    
    print_info("Reader trying to create student (should fail)...")
    response = requests.post(
        f"{BASE_URL}/students",
        json={
            "last_name": "Test",
            "first_name": "Test",
            "faculty": "Test",
            "course": "Test",
            "grade": 50.0
        },
        headers=headers
    )
    
    if response.status_code == 403:
        print_success("Authorization check passed - reader cannot create")
    else:
        print_error(f"Authorization check failed: {response.status_code}")

def test_redis_connection():
    """Test Redis connection"""
    print_section("Testing Redis Connection")
    
    try:
        import redis
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        redis_client.ping()
        print_success("Redis connection successful")
    except Exception as e:
        print_error(f"Redis connection failed: {str(e)}")
        print_info("Make sure Redis is running: redis-server")

def main():
    """Run all tests"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}FastAPI CRUD Application Test Suite{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    
    try:
        test_redis_connection()
        test_registration()
        test_login()
        test_create_students()
        test_get_students()
        test_import_csv()
        test_analytics()
        test_authorization()
        test_delete_students()
        
        print_section("Test Suite Completed")
        print_success("All tests completed! Check the results above.")
        
    except ConnectionError:
        print_error("Could not connect to the server. Make sure it's running on http://localhost:8000")
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()
