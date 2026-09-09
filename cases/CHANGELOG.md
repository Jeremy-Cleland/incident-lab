# Fixture versions

1.1: Before any held-out evaluation, made the standard_shifted and delayed_signal variants carry distinct observations. Shifted cases have different error/latency values and incident timestamps; delayed cases include a stale passing probe and explicitly delayed log delivery. No expected labels or development fixtures changed. Version 1.0 is retained in Git and its manifest is retained here. The first development smoke test used 1.0.

Both splits are synthetic and closely related templates. Held-out performance measures generalization across these perturbations, not across unseen real-world incident types.
