"""Google One Student SheerID verifier."""
import logging
import random
import re
from typing import Dict, Optional, Tuple

import httpx

from . import config
from .img_generator import generate_image, generate_psu_email
from .name_generator import NameGenerator, generate_birth_date

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)


class SheerIDVerifier:
    """Dedicated Google One Student verifier."""

    def __init__(self, install_page_url: str, verification_id: Optional[str] = None):
        self.install_page_url = self.normalize_url(install_page_url)
        self.verification_id = verification_id
        self.external_user_id = self.parse_external_user_id(self.install_page_url)
        self.device_fingerprint = self._generate_device_fingerprint()
        self.http_client = httpx.Client(timeout=30.0)

    def __del__(self):
        if hasattr(self, "http_client"):
            self.http_client.close()

    @staticmethod
    def _generate_device_fingerprint() -> str:
        chars = "0123456789abcdef"
        return "".join(random.choice(chars) for _ in range(32))

    @staticmethod
    def normalize_url(url: str) -> str:
        return url.strip()

    @staticmethod
    def parse_verification_id(url: str) -> Optional[str]:
        match = re.search(r"verificationId=([a-f0-9]+)", url, re.IGNORECASE)
        return match.group(1) if match else None

    @staticmethod
    def parse_external_user_id(url: str) -> Optional[str]:
        match = re.search(r"externalUserId=([^&]+)", url, re.IGNORECASE)
        return match.group(1) if match else None

    def _sheerid_request(
        self, method: str, url: str, body: Optional[Dict] = None
    ) -> Tuple[Dict, int]:
        response = self.http_client.request(
            method=method,
            url=url,
            json=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}
        return data, response.status_code

    def create_verification(self) -> str:
        body = {
            "programId": config.PROGRAM_ID,
            "installPageUrl": self.install_page_url,
        }
        data, status = self._sheerid_request(
            "POST", f"{config.MY_SHEERID_URL}/rest/v2/verification/", body
        )
        if status != 200 or not isinstance(data, dict) or not data.get("verificationId"):
            raise Exception(f"Failed to create verification (status {status}): {data}")

        self.verification_id = data["verificationId"]
        logger.info("Created verificationId: %s", self.verification_id)
        return self.verification_id

    def _submit_student_info(
        self,
        first_name: str,
        last_name: str,
        birth_date: str,
        email: str,
        school_id: str,
        school: Dict,
    ) -> Tuple[Dict, int]:
        payload = {
            "firstName": first_name,
            "lastName": last_name,
            "birthDate": birth_date,
            "email": email,
            "phoneNumber": "",
            "organization": {
                "id": int(school_id),
                "idExtended": school["idExtended"],
                "name": school["name"],
            },
            "deviceFingerprintHash": self.device_fingerprint,
            "externalUserId": self.external_user_id,
            "locale": "en-US",
            "metadata": {
                "marketConsentValue": False,
                "refererUrl": self.install_page_url,
                "externalUserId": self.external_user_id,
                "verificationId": self.verification_id,
                "flags": '{"collect-info-step-email-first":"default","doc-upload-considerations":"default","doc-upload-may24":"default","doc-upload-redesign-use-legacy-message-keys":false,"docUpload-assertion-checklist":"default","font-size":"default","include-cvec-field-france-student":"not-labeled-optional"}',
                "submissionOptIn": "By submitting this information, I acknowledge it may be processed to verify offer eligibility.",
            },
        }
        return self._sheerid_request(
            "POST",
            f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/collectStudentPersonalInfo",
            payload,
        )

    def _upload_to_s3(self, upload_url: str, img_data: bytes) -> bool:
        try:
            response = self.http_client.put(
                upload_url,
                content=img_data,
                headers={"Content-Type": "image/png"},
                timeout=60.0,
            )
            return 200 <= response.status_code < 300
        except Exception:
            return False

    def _build_profile(self) -> Tuple[str, str, str, str, str, Dict]:
        name = NameGenerator.generate()
        first_name = name["first_name"]
        last_name = name["last_name"]
        email = generate_psu_email(first_name, last_name)
        birth_date = generate_birth_date()
        school_id = random.choice(list(config.SCHOOLS.keys()))
        school = config.SCHOOLS[school_id]
        return first_name, last_name, email, birth_date, school_id, school

    def verify(self) -> Dict:
        try:
            if not self.external_user_id:
                self.external_user_id = str(random.randint(1000000, 9999999))
            if not self.verification_id:
                self.create_verification()

            first_name, last_name, email, birth_date, school_id, school = self._build_profile()
            img_data = generate_image(first_name, last_name, school_id)
            file_size = len(img_data)

            step2_data, step2_status = self._submit_student_info(
                first_name, last_name, birth_date, email, school_id, school
            )

            if step2_status != 200:
                raise Exception(f"Step 2 failed (status {step2_status}): {step2_data}")

            if isinstance(step2_data, dict) and step2_data.get("currentStep") == "error":
                error_ids = step2_data.get("errorIds", ["unknown_error"])
                if "fraudRulesReject" in error_ids:
                    logger.warning("fraudRulesReject on first profile, retrying with fresh profile")
                    self.device_fingerprint = self._generate_device_fingerprint()
                    self.external_user_id = str(random.randint(1000000, 9999999))

                    first_name, last_name, email, birth_date, school_id, school = self._build_profile()
                    img_data = generate_image(first_name, last_name, school_id)
                    file_size = len(img_data)

                    step2_data, step2_status = self._submit_student_info(
                        first_name, last_name, birth_date, email, school_id, school
                    )
                    if step2_status != 200:
                        raise Exception(f"Step 2 retry failed (status {step2_status}): {step2_data}")
                    if isinstance(step2_data, dict) and step2_data.get("currentStep") == "error":
                        err = ", ".join(step2_data.get("errorIds", ["unknown_error"]))
                        raise Exception(f"Step 2 rejected after retry: {err}")
                else:
                    err = ", ".join(error_ids)
                    raise Exception(f"Step 2 rejected: {err}")

            current_step = step2_data.get("currentStep", "") if isinstance(step2_data, dict) else ""
            if current_step in ["sso", "collectStudentPersonalInfo"]:
                self._sheerid_request(
                    "DELETE",
                    f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/sso",
                )

            step4_payload = {
                "files": [
                    {
                        "fileName": "student_card.png",
                        "mimeType": "image/png",
                        "fileSize": file_size,
                    }
                ]
            }
            step4_data, step4_status = self._sheerid_request(
                "POST",
                f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/docUpload",
                step4_payload,
            )
            if step4_status != 200 or not step4_data.get("documents"):
                raise Exception(f"Could not get upload URL: {step4_data}")

            upload_url = step4_data["documents"][0].get("uploadUrl")
            if not upload_url:
                raise Exception("Upload URL missing in docUpload response")
            if not self._upload_to_s3(upload_url, img_data):
                raise Exception("S3 upload failed")

            complete_data, complete_status = self._sheerid_request(
                "POST",
                f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/completeDocUpload",
            )
            if complete_status != 200:
                raise Exception(f"completeDocUpload failed (status {complete_status}): {complete_data}")

            final_data, _ = self._sheerid_request(
                "GET",
                f"{config.MY_SHEERID_URL}/rest/v2/verification/{self.verification_id}",
            )

            final_step = final_data.get("currentStep") if isinstance(final_data, dict) else None
            pending = final_step != "success"
            return {
                "success": True,
                "pending": pending,
                "message": "Document submitted, pending review" if pending else "Verification completed",
                "verification_id": self.verification_id,
                "redirect_url": final_data.get("redirectUrl") if isinstance(final_data, dict) else None,
                "status": final_data,
            }

        except Exception as e:
            logger.error("Google One verification failed: %s", e)
            return {
                "success": False,
                "message": str(e),
                "verification_id": self.verification_id,
            }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1].strip()
    else:
        url = input("Enter Google One SheerID URL: ").strip()

    if not url:
        print("No URL provided")
        raise SystemExit(1)

    verifier = SheerIDVerifier(url, verification_id=SheerIDVerifier.parse_verification_id(url))
    result = verifier.verify()
    print(result)
