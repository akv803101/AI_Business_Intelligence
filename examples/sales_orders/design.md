# Dashboard design (proposed)

**Order Performance Leadership Dashboard** for Executive leadership and sales and operations heads who need a quick read on revenue, order volume, fulfillment and delivery quality. Comparison: month_over_month.

The top row gives leaders six headline numbers covering revenue, volume, order value, customer base, fulfillment and late delivery, with Net Revenue first at top-left. Below that, monthly trend lines show direction over time. Bars break results down by year, segment, priority and status, and these use only dimensions with few values so they stay readable. The AI narrative follows the charts to explain what changed, and the caveats footer states what the data cannot show.

Filters: f_month (ORDER_MONTH), f_status (O_ORDERSTATUS), f_priority (O_ORDERPRIORITY), f_segment (C_MKTSEGMENT), f_nation (C_NATIONKEY)

```
|header----------------------------------------------------------------|
|----------------------------------------------------------------------|
|----------||----------||----------||----------||----------||----------|
|Net Revenu||Total Orde||Average Or||Active Cus||Order Fulf||Late Line |
|----------||----------||----------||----------||----------||----------|
|----------------------------------||----------------------------------|
|                                  ||                                  |
|Net Revenue by Month (currency uni||Total Orders by Month (number of o|
|                                  ||                                  |
|                                  ||                                  |
|----------------------------------||----------------------------------|
|----------------------------------||----------------------------------|
|                                  ||                                  |
|Average Order Value by Month (curr||Late Line Rate by Month (% of orde|
|                                  ||                                  |
|                                  ||                                  |
|----------------------------------||----------------------------------|
|----------------------------------||----------------------------------|
|                                  ||                                  |
|Returned Line Rate by Order Year (||Net Revenue by Customer Market Seg|
|                                  ||                                  |
|                                  ||                                  |
|----------------------------------||----------------------------------|
|----------------------------------||----------------------------------|
|                                  ||                                  |
|Late Line Rate by Order Priority (||Total Orders by Order Status (numb|
|                                  ||                                  |
|                                  ||                                  |
|----------------------------------||----------------------------------|
|----------------------------------------------------------------------|
|                                                                      |
|narrative                                                             |
|                                                                      |
|----------------------------------------------------------------------|
|footer----------------------------------------------------------------|
|----------------------------------------------------------------------|
```

| Item | Type | Shows |
|---|---|---|
| header | text | {{title}} — {{period_label}} |
| Net Revenue | kpi | Net Revenue |
| Total Orders | kpi | Total Orders |
| Average Order Value | kpi | Average Order Value |
| Active Customers | kpi | Active Customers |
| Order Fulfillment Rate | kpi | Order Fulfillment Rate |
| Late Line Rate | kpi | Late Line Rate |
| Net Revenue by Month (currency units) | line | Net Revenue by ORDER_MONTH |
| Total Orders by Month (number of orders) | line | Total Orders by ORDER_MONTH |
| Average Order Value by Month (currency units per order) | line | Average Order Value by ORDER_MONTH |
| Late Line Rate by Month (% of order lines) | line | Late Line Rate by ORDER_MONTH |
| Returned Line Rate by Order Year (% of order lines) | bar | Returned Line Rate by ORDER_YEAR |
| Net Revenue by Customer Market Segment (currency units) | bar | Net Revenue by C_MKTSEGMENT |
| Late Line Rate by Order Priority (% of order lines) | bar | Late Line Rate by O_ORDERPRIORITY |
| Total Orders by Order Status (number of orders) | bar | Total Orders by O_ORDERSTATUS |
| narrative | text | {{narrative}} |
| footer | text | {{caveats}} |
