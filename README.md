# Devjrekh API

Flask API with `/getUserData` endpoint.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

The server will run on `http://0.0.0.0:3000`

## API Endpoint

### POST `/getUserData`

**Request Body:**
```json
{
  "uuid": "0bd75917-8640-4592-8fff-b8457522e18f"
}
```

**Responses:**

1. **Valid UUID (found):**
   - Status: 200
   - Returns SHA256 hash and characters at positions 37 and 53

2. **Invalid UUID format:**
   - Status: 400
   - Error: "invalid uuid"

3. **User not found:**
   - Status: 404
   - Error: "user not found"

## Test UUIDs

- `0bd75917-8640-4592-8fff-b8457522e18f` - Valid user (found)
- `18296be4-f1c7-4479-a175-531cd3afbc12` - User not found
- Any invalid format - Invalid UUID

