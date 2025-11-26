import json
import boto3
import uuid
import os
from datetime import datetime

s3 = boto3.client("s3")

BUCKET_NAME = "roomeya-upload"  # 네 S3 버킷 이름

def lambda_handler(event, context):
    try:
        # 1) 업로드될 파일 이름 생성
        # 파일명 예: uploads/students/2024-02-07-uuid.xlsx
        ext = "xlsx"
        file_key = f"uploads/{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4()}.{ext}"

        # 2) Presigned URL 생성
        presigned_url = s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": file_key,
                "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            },
            ExpiresIn=300  # URL 5분 동안만 유효
        )

        # 3) React가 업로드에 필요한 정보 반환
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type"
            },
            "body": json.dumps({
                "uploadUrl": presigned_url,
                "fileKey": file_key
            })
        }

    except Exception as e:
        print("ERROR:", e)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
