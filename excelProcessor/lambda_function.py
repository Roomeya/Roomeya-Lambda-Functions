import json
import boto3
import openpyxl
from datetime import datetime
from urllib.parse import unquote_plus

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("Roomeya-Students")

def lambda_handler(event, context):
    try:
        # S3 이벤트 정보 가져오기
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        print(f"Processing file: s3://{bucket}/{key}")

        # S3 → /tmp 다운로드  
        download_path = f"/tmp/{key.split('/')[-1]}"
        s3.download_file(bucket, key, download_path)

        # Excel 파일 읽기
        wb = openpyxl.load_workbook(download_path)
        sheet = wb.active

        headers = []
        students = []  # 저장할 학생 목록

        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i == 0:
                # 첫 행 = 컬럼명
                headers = [str(h).strip() for h in row]
                print("Headers:", headers)
            else:
                # 그 이후 = 학생 데이터 행
                row_data = dict(zip(headers, row))

                # 빈 행은 스킵
                if not row_data.get("studentId"):
                    continue

                students.append(row_data)

        print("Parsed students:", students)

        # DynamoDB 저장
        for stu in students:
            item = {
                "studentId": str(stu.get("studentId")),
                "name": stu.get("name"),
                "email": stu.get("email"),
                "gender": stu.get("gender"),
                "createdAt": datetime.utcnow().isoformat(),
                "sourceFile": key
            }

            print("Saving student:", item)
            table.put_item(Item=item)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Student Excel processed successfully",
                "totalStudents": len(students)
            })
        }

    except Exception as e:
        print("Error:", e)
        raise e