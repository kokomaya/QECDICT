import os
import json
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# Configuration
BASE_URL = os.getenv("VIO_BASE_URL", "https://vio.automotive-wan.com:446")
VIO_TOKEN = os.getenv("API_TOKEN")
VIO_USERNAME = os.getenv("API_USERNAME")

import os
import json
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
import requests

class RequestsClient:
    """Low-level HTTP client for making requests to the VIO API."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        """Construct full URL from path."""
        return f"{self.base_url}{path}"

    def post_json(self, path: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None):
        """POST request with JSON payload."""
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        return requests.post(self._url(path), headers=h, json=payload, timeout=120)

    def put_json(self, path: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None):
        """PUT request with JSON payload."""
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        return requests.put(self._url(path), headers=h, json=payload, timeout=120)

    def delete_json(self, path: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None):
        """DELETE request with JSON payload."""
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        return requests.delete(self._url(path), headers=h, json=payload, timeout=120)

    def post_form(self, path: str, data: Dict[str, Any], files: Optional[List[Any]] = None, headers: Optional[Dict[str, str]] = None):
        """POST request with form data and optional file uploads."""
        h = headers.copy() if headers else {}
        return requests.post(self._url(path), headers=h, data=data, files=files, timeout=300)
    
    def get(self, path: str, headers: Optional[Dict[str, str]] = None):
        """GET request."""
        return requests.get(self._url(path), headers=headers, timeout=120)


class VioManagementClient:
    """
    High-level client for managing VIO models and files.
    
    This client provides methods for:
    - Creating, editing, and deleting VIO models
    - Uploading, loading, and deleting files
    - Managing VIO model configurations
    """

    def __init__(self, base_url: str = None, username: str = None, token: str = None):
        """
        Initialize the VIO Management Client.

        Args:
            base_url (str, optional): VIO API base URL. Uses VIO_BASE_URL env var if not provided.
            username (str, optional): VIO username. Uses API_USERNAME env var if not provided.
            token (str, optional): VIO API token. Uses API_TOKEN env var if not provided.
        """
        self.base_url = base_url or BASE_URL
        self.username = username or VIO_USERNAME
        self.token = token or VIO_TOKEN
        self.client = RequestsClient(self.base_url)

        if not self.username or not self.token:
            raise ValueError("Username and token must be provided either as arguments or environment variables")

    def _handle_response(self, response: requests.Response, operation: str) -> Dict[str, Any]:
        """
        Handle API response and extract JSON data.

        Args:
            response: requests.Response object
            operation: Description of the operation for error messages

        Returns:
            dict: Parsed JSON response

        Raises:
            Exception: If request failed
        """
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_msg = f"{operation} failed with status {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f": {error_data.get('error', error_data)}"
            except:
                error_msg += f": {response.text[:200]}"
            raise Exception(error_msg) from e
        except json.JSONDecodeError as e:
            raise Exception(f"{operation} returned invalid JSON: {response.text[:200]}") from e

    # ======================== VIO MODEL MANAGEMENT ======================== #

    def create_vio_model(
        self,
        name: str,
        description: str,
        ai_model: str = "Default",
        is_public: bool = False,
        is_token_protected: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new VIO model with custom configuration.

        Args:
            name (str): Name of the VIO model (must be unique).
            description (str): Description of the VIO model's purpose.
            ai_model (str): AI model to use (e.g., "Default", "GPT-4o"). Defaults to "Default".
            is_public (bool): Whether the model is publicly accessible. Defaults to False.
            is_token_protected (bool): Whether the model requires token authentication. Defaults to False.

        Returns:
            dict: API response containing creation confirmation.
            
        Example:
            >>> client.create_vio_model(
            ...     name="CustomerSupport",
            ...     description="VIO model for customer support queries",
            ...     ai_model="GPT-4o",
            ...     is_public=True
            ... )
        """
        payload = {
            "type": "CREATE_VIO_MODEL",
            "username": self.username,
            "token": self.token,
            "name": name,
            "description": description,
            "ai_model": ai_model,
            "is_public": is_public,
            "is_token_protected": is_token_protected,
        }
        response = self.client.post_json("/create_vio_model", payload)
        return self._handle_response(response, f"Create VIO model '{name}'")

    def edit_vio_model(
        self,
        original_name: str,
        changed_name: Optional[str] = None,
        description: Optional[str] = None,
        ai_model: Optional[str] = None,
        is_public: Optional[bool] = None,
        is_token_protected: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Edit an existing VIO model's configuration.

        Args:
            original_name (str): Current name of the VIO model to edit.
            changed_name (str, optional): New name for the VIO model.
            description (str, optional): New description.
            ai_model (str, optional): New AI model to use.
            is_public (bool, optional): Update public access status.
            is_token_protected (bool, optional): Update token protection status.

        Returns:
            dict: API response containing update confirmation.
            
        Example:
            >>> client.edit_vio_model(
            ...     original_name="CustomerSupport",
            ...     changed_name="CustomerSupportV2",
            ...     description="Updated customer support model"
            ... )
        """
        payload = {
            "type": "EDIT_VIO_MODEL",
            "username": self.username,
            "token": self.token,
            "original_name": original_name,
        }
        
        # Only include optional parameters if they are provided
        if changed_name is not None:
            payload["changed_name"] = changed_name
        if description is not None:
            payload["description"] = description
        if ai_model is not None:
            payload["ai_model"] = ai_model
        if is_public is not None:
            payload["is_public"] = is_public
        if is_token_protected is not None:
            payload["is_token_protected"] = is_token_protected
            
        response = self.client.put_json("/edit_vio_model", payload)
        return self._handle_response(response, f"Edit VIO model '{original_name}'")

    def delete_vio_model(self, name: str) -> Dict[str, Any]:
        """
        Delete a VIO model permanently.

        Args:
            name (str): Name of the VIO model to delete.

        Returns:
            dict: API response containing deletion confirmation.
            
        Example:
            >>> client.delete_vio_model("CustomerSupport")
        """
        payload = {
            "type": "DELETE_VIO_MODEL",
            "username": self.username,
            "token": self.token,
            "name": name,
        }
        response = self.client.delete_json("/delete_vio_model", payload)
        return self._handle_response(response, f"Delete VIO model '{name}'")

    # ======================== FILE MANAGEMENT ======================== #

    def add_files(
        self, 
        file_paths: List[str], 
        vio_model: str = "Default"
    ) -> Dict[str, Any]:
        """
        Upload one or more files to a VIO model for RAG capabilities.

        Args:
            file_paths (list): List of file paths to upload.
            vio_model (str): Name of the VIO model to associate files with. Defaults to "Default".

        Returns:
            dict: API response containing upload confirmation.
            
        Example:
            >>> client.add_files(
            ...     file_paths=["docs/manual.txt", "docs/guide.txt"],
            ...     vio_model="TechSupport"
            ... )
        """
        if not isinstance(file_paths, list):
            file_paths = [file_paths]

        files = []
        for file_path in file_paths:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            file_name = os.path.basename(file_path)
            with open(file_path, 'rb') as f:
                file_content = f.read()
                # Determine content type based on extension
                if file_path.endswith('.txt'):
                    content_type = "text/plain"
                elif file_path.endswith('.pdf'):
                    content_type = "application/pdf"
                elif file_path.endswith('.docx'):
                    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif file_path.endswith('.csv'):
                    content_type = "text/csv"
                else:
                    content_type = "application/octet-stream"
                    
                files.append(('files', (file_name, file_content, content_type)))

        if not files:
            raise ValueError("No valid files to upload")
        
        form_data = {
            "type": "ADD_FILE",
            "username": self.username,
            "token": self.token,
            "vio_model": vio_model
        }
        
        response = self.client.post_form("/add_file", data=form_data, files=files)
        return self._handle_response(response, f"Add files to VIO model '{vio_model}'")

    def load_files(
        self, 
        vio_model: str = 'Default',
        files: Optional[List[str]] = None,
        all: bool = False
    ) -> Dict[str, Any]:
        """
        Process and load files for a VIO model to enable RAG capabilities.
        Files must be uploaded via add_files() before loading.

        Args:
            vio_model (str): Name of the VIO model. Defaults to 'Default'.
            files (list, optional): List of specific file names to load.
            all (bool): If True, load all uploaded files for the VIO model. Defaults to False.

        Returns:
            dict: API response confirming the file loading process.
            
        Example:
            >>> # Load specific files
            >>> client.load_files(
            ...     vio_model="TechSupport",
            ...     files=["manual.txt", "guide.txt"]
            ... )
            
            >>> # Load all files
            >>> client.load_files(vio_model="TechSupport", all=True)
        """
        payload = {
            'type': 'LOAD_FILE',
            'username': self.username,
            'token': self.token,
            'vio_model': vio_model,
            'all': all,
            'files': files if files else []
        }

        response = self.client.post_json('/load_file', payload)
        return self._handle_response(response, f"Load files for VIO model '{vio_model}'")

    def delete_files(
        self, 
        vio_model: str = "Default",
        files: Optional[List[str]] = None,
        all: bool = False
    ) -> Dict[str, Any]:
        """
        Delete files associated with a VIO model.

        Args:
            vio_model (str): Name of the VIO model. Defaults to "Default".
            files (list, optional): List of specific file names to delete.
            all (bool): If True, delete all files for the VIO model. Defaults to False.

        Returns:
            dict: API response containing deletion confirmation.
            
        Example:
            >>> # Delete specific files
            >>> client.delete_files(
            ...     vio_model="TechSupport",
            ...     files=["old_manual.txt"]
            ... )
            
            >>> # Delete all files
            >>> client.delete_files(vio_model="TechSupport", all=True)
        """
        payload = {
            "type": "DELETE_FILE",
            "username": self.username,
            "token": self.token,
            "vio_model": vio_model,
            "files": files if files else [],
            "all": all,
        }
        
        response = self.client.post_json("/delete_file", payload)
        return self._handle_response(response, f"Delete files from VIO model '{vio_model}'")


# ======================== UTILITY FUNCTIONS ======================== #

def ensure_test_file(path: str):
    """Create a test text file if it doesn't exist."""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("""VIO Management API Test Document
=====================================

This is a test document for the VIO Management API.

Introduction
------------
This document contains sample content to test the VIO file upload,
loading, and deletion functionality.

Key Features
------------
1. VIO Model Creation and Management
2. File Upload and Processing
3. RAG (Retrieval-Augmented Generation) Capabilities
4. File Deletion and Cleanup

Technical Details
-----------------
The VIO API supports various file formats including:
- Text files (.txt)
- PDF documents (.pdf)
- Word documents (.docx)
- CSV files (.csv)

Conclusion
----------
This test file demonstrates the basic file handling capabilities
of the VIO Management API.
""")
        print(f"✓ Created test file: {path}")


def pretty_print(title: str, data: Dict[str, Any]):
    """Pretty print API response data."""
    print(f"\n{'='*60}")
    print(f"[{title}]")
    print('='*60)
    print(json.dumps(data, indent=2))


# ======================== EXAMPLE USAGE ======================== #

def example_vio_management_workflow():
    """
    Complete example workflow demonstrating VIO model and file management.
    
    Workflow:
    1. Create a new VIO model
    2. Add files to the VIO model
    3. Load files for RAG capabilities
    4. Edit VIO model configuration
    5. Delete specific files
    6. Delete the VIO model (cleanup)
    """
    print("\n" + "="*60)
    print("VIO MANAGEMENT TEMPLATE - Example Workflow")
    print("="*60)

    # Initialize client
    try:
        client = VioManagementClient()
        print(f"✓ Connected to VIO API at: {client.base_url}")
    except Exception as e:
        print(f"✗ Failed to initialize client: {e}")
        return

    vio_name = "TestVIO Management"
    test_file_path = "test_documents/sample.txt"

    try:
        # 1. Create a VIO model
        print("\n[1/6] Creating VIO model...")
        result = client.create_vio_model(
            name=vio_name,
            description="Test VIO model for management API demonstration",
            ai_model="Default",
            is_public=False,
            is_token_protected=False
        )
        pretty_print("CREATE VIO MODEL", result)

        # 2. Add files
        print("\n[2/6] Uploading files...")
        ensure_test_file(test_file_path)
        result = client.add_files(
            file_paths=[test_file_path],
            vio_model=vio_name
        )
        pretty_print("ADD FILES", result)

        # 3. Load files
        print("\n[3/6] Loading files for RAG...")
        file_name = os.path.basename(test_file_path)
        result = client.load_files(
            vio_model=vio_name,
            files=[file_name],
            all=False
        )
        pretty_print("LOAD FILES", result)

        # 4. Edit VIO model
        print("\n[4/6] Editing VIO model...")
        edited_name = f"{vio_name} v2"
        result = client.edit_vio_model(
            original_name=vio_name,
            changed_name=edited_name,
            description="Updated description for test VIO model",
            is_public=False
        )
        pretty_print("EDIT VIO MODEL", result)

        # 5. Delete files
        print("\n[5/6] Deleting files...")
        result = client.delete_files(
            vio_model=edited_name,
            files=[file_name],
            all=False
        )
        pretty_print("DELETE FILES", result)

        # 6. Delete VIO model (cleanup)
        print("\n[6/6] Deleting VIO model (cleanup)...")
        result = client.delete_vio_model(edited_name)
        pretty_print("DELETE VIO MODEL", result)

        print("\n" + "="*60)
        print("✓ VIO Management workflow completed successfully!")
        print("="*60)

    except Exception as e:
        print(f"\n✗ Error during workflow: {e}")
        # Cleanup attempt
        try:
            client.delete_vio_model(vio_name)
        except:
            pass
        try:
            client.delete_vio_model(f"{vio_name} v2")
        except:
            pass


if __name__ == "__main__":
    example_vio_management_workflow()
