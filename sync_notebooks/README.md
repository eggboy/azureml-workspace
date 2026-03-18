# Sync Notebooks (File Share → Blob Storage)

Sync notebooks from Azure ML's file share (`workspacefilestore`) to blob storage (`workspaceblobstore`) so they can be used in Azure ML Jobs.

## Background

Azure ML stores notebooks in a file share registered as the `workspacefilestore` datastore. However, Jobs can only read code from blob storage (`workspaceblobstore`). This script bridges the gap by syncing `.ipynb` files from the file share to a `notebooks_fileshare/` folder in blob storage.

## Prerequisites

### RBAC roles

Your identity needs the following roles on the workspace's storage account:

| Role | Purpose |
|---|---|
| **Storage File Data SMB Share Reader** | Read notebooks from the file share |
| **Storage Blob Data Contributor** | Write notebooks to blob storage |

Assign them with:

```bash
ASSIGNEE="<your-user-or-sp-object-id>"
STORAGE_SCOPE="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<storage-account>"

az role assignment create --assignee "$ASSIGNEE" --role "Storage File Data SMB Share Reader" --scope "$STORAGE_SCOPE"
az role assignment create --assignee "$ASSIGNEE" --role "Storage Blob Data Contributor" --scope "$STORAGE_SCOPE"
```

> RBAC propagation takes ~5 minutes after assignment.

## Usage

```bash
uv run sync_notebooks/sync_notebooks.py
```

The script will:

1. Discover storage account, file share, and blob container names from the AzureML workspace datastores
2. Authenticate using `DefaultAzureCredential` (Azure CLI, managed identity, etc.)
3. Recursively sync all `.ipynb` files from the file share to `<blob-container>/notebooks_fileshare/`

### Reference synced notebooks in a Job

```python
from azure.ai.ml import command, Input

job = command(
    code="./src",
    command="papermill ${{inputs.notebooks}}/my_notebook.ipynb output.ipynb",
    inputs={
        "notebooks": Input(
            type="uri_folder",
            path="azureml://datastores/workspaceblobstore/paths/notebooks_fileshare/",
        )
    },
    environment="azureml:my-env:1",
    compute="my-cluster",
)
```
