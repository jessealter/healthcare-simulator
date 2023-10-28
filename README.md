# Healthcare Simulator

This is a simulator to help individuals select the best healthcare plan for their needs. If you have access to multiple healthcare plans, you can use this simulator to forecast your healthcare costs under each plan, in order to minimize your costs.

# Usage

```
usage: healthsim.py [-h] [--healthcare_plans HEALTHCARE_PLANS] [--service_prices SERVICE_PRICES] [--utilization UTILIZATION]

options:
  -h, --help            show this help message and exit
  --healthcare_plans HEALTHCARE_PLANS, -hp HEALTHCARE_PLANS
                        Path to healthcare plans YAML file
  --service_prices SERVICE_PRICES, -sp SERVICE_PRICES
                        Path to service prices YAML file
  --utilization UTILIZATION, -u UTILIZATION
                        Path to utilization YAML file
```

You can use the YAML files in the `scenarios` directory to get a feel for the necessary schema.

# Limitations

Please note that this simulator is currently in development. You may encounter bugs or known issues that could affect its accuracy or usefulness. Think of this as "preview-grade" software — not yet finalized, but ready for initial feedback and testing.

This simulator is not a substitute for professional advice. Always seek guidance from a qualified professional for significant financial and healthcare decisions.

When making financial decisions, remember that the future holds inherent uncertainties. The actual healthcare costs you incur could differ from those projected by the simulator. Using your historical utilization and cost data may provide valuable insights, but it is not a guarantee of future costs.

The simulator focuses on the financial impact of different healthcare plans but does not account for other vital considerations, such as the quality of a plan's network, the comprehensiveness of coverage, or the insurer's customer support. Some individuals may prefer to avoid the use of a high deductible plan, since an substantial medical expense early in the year could impose an unexpected financial strain. Conversely, you might prefer the ease of copays associated with a low-deductible plan, but you could then miss out on potential tax advantages and the savings that come with funding a health savings account. The decision is ultimately yours, based on the factors that you value most.

# Known issues

Current known limitations in the similar include:

## Network and Service Variability

* Utilization profiles do not account for providers who may be in-network for some plans but not others.
* The simulator does not distinguish between formulary or non-formulary drugs for specific plans or networks.

## Cost Calculations and Assumptions

* Services costs cannot yet be differentiated by visit purpose, the provider's specialty, or credentials. The simulator does not yet let you specify sub-types of services that have different costs. You may use a weighted average as a workaround. For example:
    If a cardiologist charges $160 and you see them twice, and a dermatologist charges $120 and you see them once, you may calculate a weighted average as:
    `(160 * 2 + 120 * 1) / (2 + 1)` = $146.67
* The simulator does not distinguish out-of-network prescription benefits and treats all prescription utilization as in-network.
* The simulator does not support "member pays the difference" plans for pharmacy costs. It's assumed that if the utilization profile lists a brand drug, then the plan will cover that cost at the brand rate, even if a generic is available.

## Pharmacy Cost Structures

* Prescription costs may vary, even for the same drug. The simulator only uses one price you provide. List duplicate medications with different names if you need to track the price at different pharmacies, dosage levels, supply duration, or retail vs. mail-order fulfillment.
* The deductible is always assumed to apply to pharmacy costs, ignoring plans with separate prescription deductibles.

## Plan Structures and Coverage

* Some plans maintain a separate deductible for prescriptions, or for specific classes of services. The simulator tracks an in-network and optional out-of-network deductible balance, but does not track other deductible balances.
* Habilitation services are not defined in the provided YAML files. Many plans treat the pricing for habilitation services the same as rehabilitation services, so you may wish to temporarily code habilitation services as rehabilitation services in your utilization profile.
* Children's glasses are not defined in the provided YAML files. Plans typically cover children's eye exams only, but a few do cover glasses.
* Some plans may provide a premium cost structure that is more complex than 1, 2, or 3+ family members. In particular, plans sometimes offer a different price for employee + child vs. employee + spouse. The simulator does not currently support this.

# Contributing

Contributions are welcome. Please submit a pull request. Be sure to include tests for any new functionality. Or, consider just adding tests. Tests can be added purely to increase code coverage or to illustrate different healthcare scenarios.

Bug reports are also welcome. Please submit these as a GitHub issue. Be sure to include steps to reproduce the issue and any relevant logs. This is a hobby project, so I will address these issues on a best-effort basis when time permits.

# License

This project is licensed under the MIT License. See the LICENSE file for details.
