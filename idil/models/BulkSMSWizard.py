from odoo import models, fields, api
import base64
import tempfile

import requests
import urllib.parse  # For encoding message content


class BulkSMSWizard(models.TransientModel):
    _name = "bulk.sms.wizard"
    _description = "Bulk SMS Sending Wizard"

    file = fields.Binary("Upload Excel File", required=True)
    message = fields.Text("Message", required=True, help="Enter the message to send")
    sender_id = fields.Char("Sender ID", required=True, default="Dr Abdalla")
    response_file = fields.Binary("Response File", readonly=True)
    response_filename = fields.Char("Response Filename", readonly=True)
    is_unicode = fields.Boolean(
        "Use Unicode",
        help="Check this if your message contains non-English characters.",
    )

    def send_bulk_sms(self):
        """Read Excel file and send messages via 1s2u API"""
        self.ensure_one()

        # Decode file and save temporarily
        file_data = base64.b64decode(self.file)
        temp_file_path = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx").name
        with open(temp_file_path, "wb") as f:
            f.write(file_data)

        # Read Excel file
        df = pd.read_excel(temp_file_path)

        # Check if 'Mobile' column exists
        if "Mobile" not in df.columns:
            raise ValueError("Excel file must contain a 'Mobile' column.")

        # API Configuration
        url = "https://api.1s2u.io/bulksms"
        username = "dradrabe4mvj2024"
        password = "Vo0wClli"
        message_type = 0  # Unicode = 1, English = 0

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        success_count = 0
        failed_count = 0
        responses = []  # List to store response texts

        # **Format the message**
        formatted_message = self.message.replace("\n", " ")  # Remove newlines
        encoded_message = urllib.parse.quote(
            formatted_message
        )  # URL encode the message

        # **Validate sender name length compliance**
        if self.sender_id:
            if self.sender_id.isnumeric() and len(self.sender_id) > 15:
                raise ValueError("Numeric sender names must be 15 characters or less.")
            elif len(self.sender_id) > 11:
                raise ValueError(
                    "Alphanumeric sender names must be 11 characters or less."
                )

        # **Process mobile numbers**
        mobiles = df["Mobile"].dropna().astype(str).tolist()
        mobiles = [
            m.strip().replace("+", "").replace(" ", "")
            for m in mobiles
            if m.isnumeric()
        ]

        if not mobiles:
            raise ValueError("No valid mobile numbers found in the file.")

        # **Batch process numbers (Max 30 per request)**
        batch_size = 30
        for i in range(0, len(mobiles), batch_size):
            batch_numbers = ",".join(mobiles[i : i + batch_size])

            # **Construct API request**
            payload = (
                f"username={username}&password={password}"
                f"&mt={message_type}&sid={self.sender_id}"
                f"&mno={batch_numbers}&msg={encoded_message}"
            )
            response = requests.post(url, headers=headers, data=payload)
            response_text = response.text.strip()

            # **Check response status**
            if response.status_code == 200 and response_text.startswith("OK"):
                success_count += len(batch_numbers.split(","))
            else:
                failed_count += len(batch_numbers.split(","))

            # **Append API response log**
            responses.append(f"Batch {i // batch_size + 1}: {response_text}")

        # **Save responses to a text file**
        temp_txt_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        with open(temp_txt_file.name, "w", encoding="utf-8") as txt_file:
            txt_file.write("\n".join(responses))

        # **Convert the text file to Base64**
        with open(temp_txt_file.name, "rb") as f:
            encoded_file = base64.b64encode(f.read()).decode("utf-8")

        # **Save response file to Odoo**
        self.write(
            {
                "response_file": encoded_file,
                "response_filename": "bulk_sms_response.txt",
            }
        )

        # **Provide a download link**
        download_url = f"/web/content/{self.id}/response_file/{self.response_filename}?download=true"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Bulk SMS Sent",
                "message": (
                    f"Success: {success_count}, Failed: {failed_count}<br/>"
                    f"<a href='{download_url}' target='_blank'>Download Response File</a>"
                ),
                "sticky": True,  # Keeps the message visible until dismissed
                "danger": failed_count > 0,  # Highlight in red if failures exist
            },
        }
