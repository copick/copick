**Set up your static project**

In the case of CZ cryoET data portal datasets, setting up the static project is as easy as specifying one or multiple
dataset IDs. The below example selects runs from datasets 10301 and 10302.

```json
{
  "dataset_ids": [
    10301,
    10302
  ]
}
```

!!! note "Configuration Type"
    When using the CZ cryoET data portal, the `config_type`-field should be set to `cryoet-data-portal`.
