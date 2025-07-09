# Implementation Guide: Adding Parameter Format Support

This document explains how to implement the `parameter_format` field in the WhatsApp templates to ensure compatibility with Meta requirements.

## Background

Meta requires consistent parameter formatting in WhatsApp templates. When a template is declared with `parameter_format: "NAMED"`, all variables must use named format like `{{cart_id}}` rather than positional format like `{{0}}`.

## Implementation Steps

### 1. Update Database Models

The database model has been updated to include a `parameter_format` field:

- Added a new enum `ParameterFormat` with values `NAMED` and `POSITIONAL`
- Added a new column `parameter_format` to the `predefined_templates` table

### 2. Update Pydantic Schemas

The Pydantic schemas have been updated to include the `parameter_format` field:

- Added the field to `PredefinedTemplateCreate`
- Added the field to `PredefinedTemplateUpdate`
- Added the field to `PredefinedTemplateResponse`
- Added the field to `PredefinedTemplateFilter`

### 3. Database Migration

A new migration has been created to add the `parameter_format` column to the database:

```bash
# Run the migration
alembic upgrade head
```

### 4. Update Existing Templates

Run the provided script to update existing templates with the appropriate `parameter_format` value:

```bash
# Run the update script
python scripts/update_template_parameter_format.py
```

## Validation Rules

When submitting templates to Meta, ensure the following:

1. If a template uses `parameter_format: "NAMED"`, all variables must use the named format:
   - Body: `Hi {name}, your order is ready!`
   - URLs: `https://example.com/order/{order_id}`
   - Example values: `"name": "John", "order_id": "12345"`

2. If a template uses `parameter_format: "POSITIONAL"`, all variables must use the positional format:
   - Body: `Hi {0}, your order is ready!`
   - URLs: `https://example.com/order/{1}`
   - Example values: `"0": "John", "1": "12345"`

3. A template cannot mix named and positional parameters.

## Frontend Updates

Make sure the frontend validates that:

1. Template parameters in URLs match the pattern specified by `parameter_format`
2. Example values match the parameter names in the template
3. Display appropriate validation errors if parameters are mismatched

## Testing

To verify the implementation:

1. Create a new template with `parameter_format: "NAMED"` and ensure all variables use named format
2. Edit an existing template to update URLs from positional to named format
3. Attempt to create a template with mismatched parameter formats and verify validation errors
4. Filter templates by `parameter_format` to ensure the field is being properly stored and retrieved 