# Security, reliability and limitations

## Readiness

| Level | Status |
| --- | --- |
| A. Professional demo with synthetic data | Intended level of this work. All data is fictional and labelled as such. |
| B. Controlled pilot | **Not ready.** Needs authentication, durable storage, a private message broker, monitoring and a data-handling agreement. |
| C. Real industrial production | **Not ready.** Needs a separate security, infrastructure, integration and engineering-safety review. |

## Security

| Area | Current state | Needed before real data |
| --- | --- | --- |
| Access | No login; anyone with the URL can use the app | Authentication and roles (operator, engineer, manager) |
| Storage | SQLite files on the container disk (platform and Brain); may be wiped on restart | Managed database with backups and retention policy |
| Live sensor link | Public MQTT brokers, topic secured only by a 6-digit code; TLS to broker | Private broker with authentication and per-device credentials; never public brokers |
| Third-party scripts | mqtt.js and a QR library from unpkg, no integrity hashes | Self-host or pin with SRI |
| Injection | User text is escaped where rendered as HTML; history import validated | Security review of all HTML injection points |
| Knowledge store | Outcome records require a role and mechanism; no identity check | Tie outcomes to authenticated users; audit log |

## Reliability

* A failing page, or a failing Brain stage, is contained: the error is shown and logged and
  the rest of the platform keeps working (tested).
* The Brain fingerprints the original observations before and after each run.
* Results are recomputed on every view (about 25–45 ms per case), so a shown result is never
  stale; the fleet table is cached for at most 60 s.

## Engineering limitations

* All three P-301 scenarios and the Brain fixtures are synthetic.
* Rules exist for one asset type (centrifugal pump); other types are reported as unsupported.
* A 48-hour window cannot show long-term degradation; no remaining useful life is estimated.
* Confidence is evidence strength from hand-written weights, not a calibrated probability.
* Calibration status is known only for the vibration transmitter.
* Typical-indicator matching organises the review; it does not prove a mechanism.
* Recommendations are decision support for qualified engineers. They never authorise
  starting, stopping or modifying equipment.
