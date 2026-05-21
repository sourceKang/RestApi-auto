# NeoX Invalid Profile Cases

Reserved for per-profile negative test data.

Suggested shape:

```json
{
  "cases": [
    {
      "name": "invalid_field",
      "payload": {
        "Content": {
          "__invalid_field__": "invalid"
        }
      },
      "expected": {
        "retstatus": "Fail",
        "message_contains": ["invalid field"]
      }
    }
  ]
}
```
