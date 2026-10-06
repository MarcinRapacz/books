# REST API input is validated by default in controllers

> Source: https://docs.strapi.io/cms/migration/v4-to-v5/breaking-changes/default-input-validation

In Strapi 5, REST API input is validated by default in controllers instead of being silently sanitized, throwing `400 Bad Request` errors for invalid data like unrecognized fields and unpermitted relations.

Sanitization means that the object is “cleaned” and returned.

Validation means an assertion is made that the data is already clean and throws an error if something is found that shouldn't be there.

Strapi methods exist both for [sanitization and validation in controllers](/cms/backend-customization/controllers#sanitization-and-validation-in-controllers) and they can target input body data, query parameters, and output (only for sanitization).

In Strapi 5, REST API input is validated by default in controllers, instead of accepting invalid data and sanitizing it silently.

This page is part of the [breaking changes database](/cms/migration/v4-to-v5/breaking-changes) and provides information about the breaking change and additional instructions to migrate from Strapi v4 to Strapi 5.

- Is this breaking change affecting plugins? Yes
- Is this breaking change automatically handled by a codemod? No

## Breaking change description

**In Strapi v4**

In v4, query parameters are validated, but input data (create and update body data) is only sanitized.

**In Strapi 5**

In v5, both query parameters and input data are validated.

## Migration

This section regroups useful notes and procedures about the introduced breaking change.

### Notes

* A `400 Bad Request` error will be thrown if the request has invalid values such as in the following cases:

  - relations the user do not have permission to create
  - unrecognized values that are not present on a schema
  - attempt to writing non-writable fields and internal timestamps like `createdAt` and `createdBy` fields
  - usage of the `id` field (other than for connecting relations) to set or update the `id` of an object

### Manual procedure

Users should ensure that parameters and input data are valid to avoid `400` errors being thrown. Additional information can be found in the [sanitization and validation in controllers](/cms/backend-customization/controllers#sanitization-and-validation-in-controllers) documentation.
