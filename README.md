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

You can use the YAML files in the `scenarios` directory to get a feel for the necessary schema. The full plan and utilization schema (including support for plan quirks like waived ER copays, day limits, drug-category copay overrides, and generic substitution) is documented in the `healthsim.py` module docstring.

# Plan features

Beyond plain copay/coinsurance tables, plans can express a number of real-world quirks:

* **Copay/deductible interaction** — `deductible_applies` on any service entry. Defaults to true for coinsurance and false for copays; high-deductible plans whose ER copay applies only after the deductible set it explicitly.
* **Admission-waived ER copays** — `waived_if_admitted: true` plus a utilization entry like `{count: 1, admitted: true}`.
* **Occurrence limits** — `limit: {max: N}` (e.g. skilled nursing facility day caps). Beyond the cap, the member pays the full price and it credits nothing.
* **Out-of-pocket maximum exclusions** — `counts_toward_oop_max: false` for services (e.g. durable medical equipment on some HMOs) whose cost sharing neither counts toward nor is capped by the OOP max.
* **Allowance benefits** — `max_plan_paid: X` (e.g. children's eyewear up to $150): the plan pays up to X, the member pays the excess.
* **Prescription drug categories** — `overrides` on the prescription entry map categories (e.g. `glp1_weight_loss`, `preventive`) to their own copay/coinsurance and deductible treatment.
* **Generic substitution** — `generic_substitution: member_pays_difference`: when the utilization profile lists a `generic_substitute` for a non-generic drug, cost sharing is computed on the generic price at the generic tier's rate and the price difference is charged uncovered. Plans without the rule ignore the field. See `scenarios/profile_brand_over_generic.yml` for a runnable example.
* **Per-network pharmacy benefits** — prescription entries exist per network level; a plan with no out-of-network pharmacy benefit simply omits the entry there.

# Limitations

This is a reasonable-effort side project for comparing healthcare plans. It is not intended to be professional-grade software. You may encounter bugs or known limitations that affect accuracy. Treat the results as napkin math: good for comparing plans side by side and sanity-checking rough annual costs, but not a precise forecast of your healthcare spending.

For transparency: generative AI is used in the development of this codebase, including code, tests, documentation, and plan data. Changes are reviewed by a human before they are merged.

This simulator is not a substitute for professional advice. Always seek guidance from a qualified professional for significant financial and healthcare decisions.

When making financial decisions, remember that the future holds inherent uncertainties. The actual healthcare costs you incur could differ from those projected by the simulator. Using your historical utilization and cost data may provide valuable insights, but it is not a guarantee of future costs.

The simulator focuses on the financial impact of different healthcare plans but does not account for other vital considerations, such as the quality of a plan's network, the comprehensiveness of coverage, or the insurer's customer support. Some individuals may prefer to avoid the use of a high deductible plan, since an substantial medical expense early in the year could impose an unexpected financial strain. Conversely, you might prefer the ease of copays associated with a low-deductible plan, but you could then miss out on potential tax advantages and the savings that come with funding a health savings account. The decision is ultimately yours, based on the factors that you value most.

# Known issues

Current known limitations in the similar include:

## Network and Service Variability

* Utilization profiles do not account for providers who may be in-network for some plans but not others.
* The simulator does not look up plan formularies. Drug tiers (`generic`, `brand_preferred`, ...) and special categories (e.g. `glp1_weight_loss`, `preventive`) are whatever your utilization profile declares; the simulator applies the plan's rate for that tier or category.

## Cost Calculations and Assumptions

* Services costs cannot yet be differentiated by visit purpose, the provider's specialty, or credentials. The simulator does not yet let you specify sub-types of services that have different costs. You may use a weighted average as a workaround. For example:
    If a cardiologist charges $160 and you see them twice, and a dermatologist charges $120 and you see them once, you may calculate a weighted average as:
    `(160 * 2 + 120 * 1) / (2 + 1)` = $146.67
* The utilization profile chooses the network level for each prescription (`network: out_of_network`). The simulator does not know which pharmacies or drugs are in network for a given plan.
* For "member pays the difference" plans, if a brand drug's utilization entry lists no `generic_substitute`, the simulator assumes the plan covers it at the brand rate even if a generic exists.

## Pharmacy Cost Structures

* Prescription costs may vary, even for the same drug. The simulator only uses one price you provide. List duplicate medications with different names if you need to track the price at different pharmacies, dosage levels, supply duration, or retail vs. mail-order fulfillment.
* Whether the deductible applies to prescriptions is plan-controlled (`deductible_applies` on the prescription entry, overridable per drug category), but the simulator still tracks only the medical deductible balance — it does not model plans with a *separate* prescription deductible amount.

## Plan Structures and Coverage

* Some plans maintain a separate deductible for prescriptions, or for specific classes of services. The simulator tracks an in-network and optional out-of-network deductible balance, but does not track other deductible balances.
* Habilitation services are not defined in the provided YAML files. Many plans treat the pricing for habilitation services the same as rehabilitation services, so you may wish to temporarily code habilitation services as rehabilitation services in your utilization profile.
* Children's glasses can be modeled with a `child_eyewear` service entry using `max_plan_paid` for the allowance; the frequency rules (e.g. once per 24 months) are up to your utilization profile to respect.
* Some plans may provide a premium cost structure that is more complex than 1, 2, or 3+ family members. In particular, plans sometimes offer a different price for employee + child vs. employee + spouse. The simulator does not currently support this.

# Contributing

Contributions are welcome. Please submit a pull request. Be sure to include tests for any new functionality. Or, consider just adding tests. Tests can be added purely to increase code coverage or to illustrate different healthcare scenarios.

Bug reports are also welcome. Please submit these as a GitHub issue. Be sure to include steps to reproduce the issue and any relevant logs. This is a hobby project, so I will address these issues on a best-effort basis when time permits.

# License

This project is licensed under the MIT License. See the LICENSE file for details.
