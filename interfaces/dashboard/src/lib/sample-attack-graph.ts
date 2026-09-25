/**
 * SAMPLE NETWORK — illustrative assets, not any real estate.
 *
 * Real `core/` engine output (`/attack-graph`, `/attack-graph/targets/*`,
 * `/assets`) captured from an invented 9-asset network: two internet-facing
 * assets in a DMZ, application, corporate, data and management segments, one
 * CVE open on both an entry point and an internal asset (to show the shared-
 * exploit correlation), and one asset with no known segment. The assets are
 * made up; the probabilities and rupee figures are what the engine computes
 * for them. Shown only when a reader opts in with `?sample=1`, under a notice
 * that says so — never mixed into the current snapshot's figures.
 *
 * Regenerate by committing that network to a scratch snapshot store, pointing
 * an API instance at it (SNAPSHOT_STORE_PATH) and saving those three responses.
 */

import type { AssetsResponse, AttackGraphResponse, AttackGraphTarget } from "./types";

export const SAMPLE_ATTACK_GRAPH: {
  graph: AttackGraphResponse;
  assets: AssetsResponse;
  targets: Record<string, AttackGraphTarget>;
} = {
 "graph": {
  "snapshot_id": "sha256:6c5479ef11fbe2cea37c201cb892cd3c976b94aa98491df3600565fa5e728cbf",
  "observed_at": "2026-09-20T00:00:00Z",
  "samples": 50000,
  "topology_declared": true,
  "segments": [
   {
    "segment_id": "dmz",
    "name": "DMZ",
    "declared": true,
    "asset_ids": [
     "asset-web-01",
     "asset-vpn-01"
    ]
   },
   {
    "segment_id": "app",
    "name": "Application tier",
    "declared": true,
    "asset_ids": [
     "asset-api-01",
     "asset-loan-app-01"
    ]
   },
   {
    "segment_id": "corp",
    "name": "Corporate LAN",
    "declared": true,
    "asset_ids": [
     "asset-hr-db-01",
     "asset-ad-01"
    ]
   },
   {
    "segment_id": "data",
    "name": "Data tier",
    "declared": true,
    "asset_ids": [
     "asset-core-db-01"
    ]
   },
   {
    "segment_id": "mgmt",
    "name": "Management",
    "declared": true,
    "asset_ids": [
     "asset-jump-01"
    ]
   }
  ],
  "segment_links": [
   {
    "from_segment_id": "dmz",
    "to_segment_id": "app"
   },
   {
    "from_segment_id": "dmz",
    "to_segment_id": "corp"
   },
   {
    "from_segment_id": "app",
    "to_segment_id": "data"
   },
   {
    "from_segment_id": "corp",
    "to_segment_id": "mgmt"
   },
   {
    "from_segment_id": "mgmt",
    "to_segment_id": "data"
   },
   {
    "from_segment_id": "mgmt",
    "to_segment_id": "app"
   }
  ],
  "edge_count": 21,
  "edges": [
   {
    "source_asset_id": "asset-web-01",
    "target_asset_id": "asset-vpn-01",
    "reason": "same_segment:dmz"
   },
   {
    "source_asset_id": "asset-vpn-01",
    "target_asset_id": "asset-web-01",
    "reason": "same_segment:dmz"
   },
   {
    "source_asset_id": "asset-hr-db-01",
    "target_asset_id": "asset-ad-01",
    "reason": "same_segment:corp"
   },
   {
    "source_asset_id": "asset-ad-01",
    "target_asset_id": "asset-hr-db-01",
    "reason": "same_segment:corp"
   },
   {
    "source_asset_id": "asset-api-01",
    "target_asset_id": "asset-loan-app-01",
    "reason": "same_segment:app"
   },
   {
    "source_asset_id": "asset-loan-app-01",
    "target_asset_id": "asset-api-01",
    "reason": "same_segment:app"
   },
   {
    "source_asset_id": "asset-web-01",
    "target_asset_id": "asset-api-01",
    "reason": "segment_reachability:dmz->app"
   },
   {
    "source_asset_id": "asset-web-01",
    "target_asset_id": "asset-loan-app-01",
    "reason": "segment_reachability:dmz->app"
   },
   {
    "source_asset_id": "asset-vpn-01",
    "target_asset_id": "asset-api-01",
    "reason": "segment_reachability:dmz->app"
   },
   {
    "source_asset_id": "asset-vpn-01",
    "target_asset_id": "asset-loan-app-01",
    "reason": "segment_reachability:dmz->app"
   },
   {
    "source_asset_id": "asset-web-01",
    "target_asset_id": "asset-hr-db-01",
    "reason": "segment_reachability:dmz->corp"
   },
   {
    "source_asset_id": "asset-web-01",
    "target_asset_id": "asset-ad-01",
    "reason": "segment_reachability:dmz->corp"
   },
   {
    "source_asset_id": "asset-vpn-01",
    "target_asset_id": "asset-hr-db-01",
    "reason": "segment_reachability:dmz->corp"
   },
   {
    "source_asset_id": "asset-vpn-01",
    "target_asset_id": "asset-ad-01",
    "reason": "segment_reachability:dmz->corp"
   },
   {
    "source_asset_id": "asset-api-01",
    "target_asset_id": "asset-core-db-01",
    "reason": "segment_reachability:app->data"
   },
   {
    "source_asset_id": "asset-loan-app-01",
    "target_asset_id": "asset-core-db-01",
    "reason": "segment_reachability:app->data"
   },
   {
    "source_asset_id": "asset-hr-db-01",
    "target_asset_id": "asset-jump-01",
    "reason": "segment_reachability:corp->mgmt"
   },
   {
    "source_asset_id": "asset-ad-01",
    "target_asset_id": "asset-jump-01",
    "reason": "segment_reachability:corp->mgmt"
   },
   {
    "source_asset_id": "asset-jump-01",
    "target_asset_id": "asset-core-db-01",
    "reason": "segment_reachability:mgmt->data"
   },
   {
    "source_asset_id": "asset-jump-01",
    "target_asset_id": "asset-api-01",
    "reason": "segment_reachability:mgmt->app"
   },
   {
    "source_asset_id": "asset-jump-01",
    "target_asset_id": "asset-loan-app-01",
    "reason": "segment_reachability:mgmt->app"
   }
  ],
  "nodes": [
   {
    "asset_id": "asset-web-01",
    "segment_id": "dmz",
    "internet_facing": true,
    "role": "entry",
    "open_finding_count": 1,
    "kev_finding_count": 1,
    "routes": []
   },
   {
    "asset_id": "asset-hr-db-01",
    "segment_id": "corp",
    "internet_facing": false,
    "role": "reachable",
    "open_finding_count": 1,
    "kev_finding_count": 0,
    "routes": [
     {
      "entry_asset_id": "asset-web-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.26378,
      "reach_given_finding": {
       "finding-0002": 0.26378
      },
      "share": 0.5878498841148155
     },
     {
      "entry_asset_id": "asset-vpn-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.18494,
      "reach_given_finding": {
       "finding-0002": 0.18494
      },
      "share": 0.4121501158851845
     }
    ]
   },
   {
    "asset_id": "asset-vpn-01",
    "segment_id": "dmz",
    "internet_facing": true,
    "role": "entry",
    "open_finding_count": 1,
    "kev_finding_count": 1,
    "routes": []
   },
   {
    "asset_id": "asset-api-01",
    "segment_id": "app",
    "internet_facing": false,
    "role": "reachable",
    "open_finding_count": 1,
    "kev_finding_count": 1,
    "routes": [
     {
      "entry_asset_id": "asset-web-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.26232,
      "reach_given_finding": {
       "finding-0004": 0.5025287356321839
      },
      "share": 0.5857449088960344
     },
     {
      "entry_asset_id": "asset-vpn-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.18552,
      "reach_given_finding": {
       "finding-0004": 0.1853639846743295
      },
      "share": 0.4142550911039657
     }
    ]
   },
   {
    "asset_id": "asset-loan-app-01",
    "segment_id": "app",
    "internet_facing": false,
    "role": "reachable",
    "open_finding_count": 1,
    "kev_finding_count": 0,
    "routes": [
     {
      "entry_asset_id": "asset-web-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.26198,
      "reach_given_finding": {
       "finding-0005": 0.26198
      },
      "share": 0.5867150407596524
     },
     {
      "entry_asset_id": "asset-vpn-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.18454,
      "reach_given_finding": {
       "finding-0005": 0.18454
      },
      "share": 0.4132849592403475
     }
    ]
   },
   {
    "asset_id": "asset-core-db-01",
    "segment_id": "data",
    "internet_facing": false,
    "role": "reachable",
    "open_finding_count": 2,
    "kev_finding_count": 0,
    "routes": [
     {
      "entry_asset_id": "asset-web-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.26066,
      "reach_given_finding": {
       "finding-0006": 0.26066,
       "finding-0007": 0.26066
      },
      "share": 0.7192207935544396
     },
     {
      "entry_asset_id": "asset-vpn-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.10176,
      "reach_given_finding": {
       "finding-0006": 0.10176,
       "finding-0007": 0.10176
      },
      "share": 0.28077920644556037
     }
    ]
   },
   {
    "asset_id": "asset-ad-01",
    "segment_id": "corp",
    "internet_facing": false,
    "role": "reachable",
    "open_finding_count": 1,
    "kev_finding_count": 1,
    "routes": [
     {
      "entry_asset_id": "asset-web-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.2601,
      "reach_given_finding": {
       "finding-0008": 0.262258064516129
      },
      "share": 0.5782827159944862
     },
     {
      "entry_asset_id": "asset-vpn-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.18968,
      "reach_given_finding": {
       "finding-0008": 1.019784946236559
      },
      "share": 0.4217172840055138
     }
    ]
   },
   {
    "asset_id": "asset-jump-01",
    "segment_id": "mgmt",
    "internet_facing": false,
    "role": "reachable",
    "open_finding_count": 0,
    "kev_finding_count": 0,
    "routes": [
     {
      "entry_asset_id": "asset-vpn-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.18614,
      "reach_given_finding": {},
      "share": 0.759879163945134
     },
     {
      "entry_asset_id": "asset-web-01",
      "entry_exposure_profile": "internet_facing_critical_asset",
      "reach_probability": 0.05882,
      "reach_given_finding": {},
      "share": 0.24012083605486612
     }
    ]
   },
   {
    "asset_id": "asset-ftp-legacy",
    "segment_id": null,
    "internet_facing": false,
    "role": "unknown",
    "open_finding_count": 1,
    "kev_finding_count": 1,
    "routes": []
   }
  ]
 },
 "assets": {
  "snapshot_id": "sha256:6c5479ef11fbe2cea37c201cb892cd3c976b94aa98491df3600565fa5e728cbf",
  "observed_at": "2026-09-20T00:00:00Z",
  "monte_carlo_iterations": 10000,
  "expected_annual_loss_inr": 261718207.44674703,
  "assets": [
   {
    "asset_id": "asset-web-01",
    "service_ids": [
     "svc-core-banking"
    ],
    "services": [
     {
      "backup": {
       "exists": true,
       "immutable_copy": true,
       "last_tested_at": "2026-08-01T00:00:00Z",
       "rpo_hours": 1,
       "rto_hours": 4
      },
      "criticality": "critical",
      "name": "Core Banking Platform",
      "service_id": "svc-core-banking"
     }
    ],
    "unresolved_service_ids": [],
    "network": {
     "internet_facing": true,
     "open_ports": [
      443
     ],
     "segment_id": "dmz"
    },
    "edr": {
     "agent_healthy": true,
     "agent_installed": true,
     "detection_rules_active": [
      "rule-web-exploit-generic"
     ],
     "recent_alerts": []
    },
    "identity_access": {
     "mfa_enforced": true,
     "privileged_accounts_count": 2
    },
    "expected_annual_loss_inr": 106334809.45361486,
    "findings": [
     {
      "cve_id": "CVE-2026-00001",
      "epss_score": 0.87,
      "kev_listed": true,
      "remediated_at": null,
      "criticality": "critical",
      "finding_id": "finding-0001",
      "first_seen_at": "2026-09-01T00:00:00Z",
      "provenance": {
       "connector": "nessus_connector",
       "raw_source_id": "nessus-plugin-999999"
      },
      "type": "cve",
      "scenario": {
       "scenario_id": "asset-web-01::finding-0001",
       "description": "cve CVE-2026-00001 on asset-web-01 (internet_facing_critical_asset, critical-tier service impact)",
       "exposure_profile": "internet_facing_critical_asset",
       "threat_event_frequency": {
        "min": 6.0,
        "most_likely": 12.0,
        "max": 24.0
       },
       "exploit_probability": 0.87,
       "active_control_resistances": {
        "mfa_enforced": 0.4,
        "edr_active": 0.5
       },
       "vulnerability": 0.261,
       "graph_reachability_applied": false,
       "attack_routes": [],
       "loss_event_frequency": {
        "min": 1.566,
        "most_likely": 3.132,
        "max": 6.264
       },
       "criticality_tier": "critical",
       "backup_posture": "backup_tested_immutable",
       "loss_magnitude": {
        "min": 5000000.0,
        "most_likely": 20000000.0,
        "max": 80000000.0
       },
       "expected_annual_loss_inr": 106334809.45361486
      }
     }
    ]
   },
   {
    "asset_id": "asset-hr-db-01",
    "service_ids": [
     "svc-internal-hr"
    ],
    "services": [
     {
      "backup": {
       "exists": false,
       "immutable_copy": null,
       "last_tested_at": null,
       "rpo_hours": null,
       "rto_hours": null
      },
      "criticality": "low",
      "name": "Internal HR Portal",
      "service_id": "svc-internal-hr"
     }
    ],
    "unresolved_service_ids": [],
    "network": {
     "internet_facing": false,
     "open_ports": null,
     "segment_id": "corp"
    },
    "edr": {
     "agent_healthy": null,
     "agent_installed": false,
     "detection_rules_active": null,
     "recent_alerts": null
    },
    "identity_access": {
     "mfa_enforced": false,
     "privileged_accounts_count": 1
    },
    "expected_annual_loss_inr": 263855.75801501836,
    "findings": [
     {
      "cve_id": null,
      "epss_score": null,
      "kev_listed": null,
      "remediated_at": null,
      "criticality": "unknown",
      "finding_id": "finding-0002",
      "first_seen_at": "2026-09-10T00:00:00Z",
      "provenance": {
       "connector": "prowler_connector",
       "raw_source_id": "prowler-check-s3-public"
      },
      "type": "misconfiguration",
      "scenario": {
       "scenario_id": "asset-hr-db-01::finding-0002",
       "description": "misconfiguration finding-0002 on asset-hr-db-01 (internal_asset, low-tier service impact); reached via attack graph: asset-web-01 59% (p=0.264), asset-vpn-01 41% (p=0.185)",
       "exposure_profile": "internal_asset",
       "threat_event_frequency": {
        "min": 2.69232,
        "most_likely": 5.38464,
        "max": 10.76928
       },
       "exploit_probability": 0.05,
       "active_control_resistances": {},
       "vulnerability": 0.05,
       "graph_reachability_applied": true,
       "attack_routes": [
        {
         "entry_asset_id": "asset-web-01",
         "share": 0.5878498841148155,
         "reach_probability": 0.26378
        },
        {
         "entry_asset_id": "asset-vpn-01",
         "share": 0.4121501158851845,
         "reach_probability": 0.18494
        }
       ],
       "loss_event_frequency": {
        "min": 0.134616,
        "most_likely": 0.269232,
        "max": 0.538464
       },
       "criticality_tier": "low",
       "backup_posture": "no_backup",
       "loss_magnitude": {
        "min": 150000.0,
        "most_likely": 600000.0,
        "max": 3000000.0
       },
       "expected_annual_loss_inr": 263855.75801501836
      }
     }
    ]
   },
   {
    "asset_id": "asset-vpn-01",
    "service_ids": [
     "svc-identity"
    ],
    "services": [
     {
      "backup": {
       "exists": true,
       "immutable_copy": false,
       "last_tested_at": "2026-08-01T00:00:00Z",
       "rpo_hours": 4,
       "rto_hours": 8
      },
      "criticality": "high",
      "name": "Directory & identity",
      "service_id": "svc-identity"
     }
    ],
    "unresolved_service_ids": [],
    "network": {
     "internet_facing": true,
     "open_ports": [
      443
     ],
     "segment_id": "dmz"
    },
    "edr": {
     "agent_healthy": true,
     "agent_installed": true,
     "detection_rules_active": [],
     "recent_alerts": []
    },
    "identity_access": {
     "mfa_enforced": true,
     "privileged_accounts_count": 1
    },
    "expected_annual_loss_inr": 24473992.221900843,
    "findings": [
     {
      "cve_id": "CVE-2026-11002",
      "epss_score": 0.62,
      "kev_listed": true,
      "remediated_at": null,
      "criticality": "high",
      "finding_id": "finding-0003",
      "first_seen_at": "2026-09-05T00:00:00Z",
      "provenance": {
       "connector": "nessus_connector",
       "raw_source_id": "x-3"
      },
      "type": "cve",
      "scenario": {
       "scenario_id": "asset-vpn-01::finding-0003",
       "description": "cve CVE-2026-11002 on asset-vpn-01 (internet_facing_critical_asset, high-tier service impact)",
       "exposure_profile": "internet_facing_critical_asset",
       "threat_event_frequency": {
        "min": 6.0,
        "most_likely": 12.0,
        "max": 24.0
       },
       "exploit_probability": 0.62,
       "active_control_resistances": {
        "mfa_enforced": 0.4,
        "edr_active": 0.5
       },
       "vulnerability": 0.18600000000000003,
       "graph_reachability_applied": false,
       "attack_routes": [],
       "loss_event_frequency": {
        "min": 1.116,
        "most_likely": 2.232,
        "max": 4.464
       },
       "criticality_tier": "high",
       "backup_posture": "backup_tested_no_immutable",
       "loss_magnitude": {
        "min": 1300000.0,
        "most_likely": 6500000.0,
        "max": 26000000.0
       },
       "expected_annual_loss_inr": 24473992.221900843
      }
     }
    ]
   },
   {
    "asset_id": "asset-api-01",
    "service_ids": [
     "svc-portal"
    ],
    "services": [
     {
      "backup": {
       "exists": true,
       "immutable_copy": false,
       "last_tested_at": "2026-08-01T00:00:00Z",
       "rpo_hours": 4,
       "rto_hours": 8
      },
      "criticality": "high",
      "name": "Customer portal",
      "service_id": "svc-portal"
     }
    ],
    "unresolved_service_ids": [],
    "network": {
     "internet_facing": false,
     "open_ports": null,
     "segment_id": "app"
    },
    "edr": {
     "agent_healthy": null,
     "agent_installed": false,
     "detection_rules_active": null,
     "recent_alerts": null
    },
    "identity_access": {
     "mfa_enforced": true,
     "privileged_accounts_count": 1
    },
    "expected_annual_loss_inr": 43868491.97040482,
    "findings": [
     {
      "cve_id": "CVE-2026-00001",
      "epss_score": 0.87,
      "kev_listed": true,
      "remediated_at": null,
      "criticality": "high",
      "finding_id": "finding-0004",
      "first_seen_at": "2026-09-05T00:00:00Z",
      "provenance": {
       "connector": "nessus_connector",
       "raw_source_id": "x-4"
      },
      "type": "cve",
      "scenario": {
       "scenario_id": "asset-api-01::finding-0004",
       "description": "cve CVE-2026-00001 on asset-api-01 (internal_asset, high-tier service impact); reached via attack graph: asset-web-01 59% (p=0.262), asset-vpn-01 41% (p=0.186)",
       "exposure_profile": "internal_asset",
       "threat_event_frequency": {
        "min": 4.1273563218390805,
        "most_likely": 8.254712643678161,
        "max": 16.509425287356322
       },
       "exploit_probability": 0.87,
       "active_control_resistances": {
        "mfa_enforced": 0.4
       },
       "vulnerability": 0.522,
       "graph_reachability_applied": true,
       "attack_routes": [
        {
         "entry_asset_id": "asset-web-01",
         "share": 0.5857449088960344,
         "reach_probability": 0.26232
        },
        {
         "entry_asset_id": "asset-vpn-01",
         "share": 0.4142550911039657,
         "reach_probability": 0.18552
        }
       ],
       "loss_event_frequency": {
        "min": 2.15448,
        "most_likely": 4.30896,
        "max": 8.61792
       },
       "criticality_tier": "high",
       "backup_posture": "backup_tested_no_immutable",
       "loss_magnitude": {
        "min": 1300000.0,
        "most_likely": 6500000.0,
        "max": 26000000.0
       },
       "expected_annual_loss_inr": 43868491.97040482
      }
     }
    ]
   },
   {
    "asset_id": "asset-loan-app-01",
    "service_ids": [
     "svc-loans"
    ],
    "services": [
     {
      "backup": {
       "exists": true,
       "immutable_copy": false,
       "last_tested_at": null,
       "rpo_hours": 4,
       "rto_hours": 8
      },
      "criticality": "critical",
      "name": "Loan management",
      "service_id": "svc-loans"
     }
    ],
    "unresolved_service_ids": [],
    "network": {
     "internet_facing": false,
     "open_ports": null,
     "segment_id": "app"
    },
    "edr": {
     "agent_healthy": true,
     "agent_installed": true,
     "detection_rules_active": [],
     "recent_alerts": []
    },
    "identity_access": {
     "mfa_enforced": true,
     "privileged_accounts_count": 1
    },
    "expected_annual_loss_inr": 20399602.325170975,
    "findings": [
     {
      "cve_id": "CVE-2026-20417",
      "epss_score": 0.21,
      "kev_listed": false,
      "remediated_at": null,
      "criticality": "high",
      "finding_id": "finding-0005",
      "first_seen_at": "2026-09-05T00:00:00Z",
      "provenance": {
       "connector": "nessus_connector",
       "raw_source_id": "x-5"
      },
      "type": "cve",
      "scenario": {
       "scenario_id": "asset-loan-app-01::finding-0005",
       "description": "cve CVE-2026-20417 on asset-loan-app-01 (internal_asset, critical-tier service impact); reached via attack graph: asset-web-01 59% (p=0.262), asset-vpn-01 41% (p=0.185)",
       "exposure_profile": "internal_asset",
       "threat_event_frequency": {
        "min": 2.67912,
        "most_likely": 5.35824,
        "max": 10.71648
       },
       "exploit_probability": 0.21,
       "active_control_resistances": {
        "mfa_enforced": 0.4,
        "edr_active": 0.5
       },
       "vulnerability": 0.063,
       "graph_reachability_applied": true,
       "attack_routes": [
        {
         "entry_asset_id": "asset-web-01",
         "share": 0.5867150407596524,
         "reach_probability": 0.26198
        },
        {
         "entry_asset_id": "asset-vpn-01",
         "share": 0.4132849592403475,
         "reach_probability": 0.18454
        }
       ],
       "loss_event_frequency": {
        "min": 0.16878456,
        "most_likely": 0.33756912,
        "max": 0.67513824
       },
       "criticality_tier": "critical",
       "backup_posture": "backup_untested",
       "loss_magnitude": {
        "min": 9000000.0,
        "most_likely": 36000000.0,
        "max": 144000000.0
       },
       "expected_annual_loss_inr": 20399602.325170975
      }
     }
    ]
   },
   {
    "asset_id": "asset-core-db-01",
    "service_ids": [
     "svc-payments",
     "svc-core-banking"
    ],
    "services": [
     {
      "backup": {
       "exists": true,
       "immutable_copy": true,
       "last_tested_at": "2026-08-01T00:00:00Z",
       "rpo_hours": 4,
       "rto_hours": 8
      },
      "criticality": "critical",
      "name": "Payments gateway",
      "service_id": "svc-payments"
     },
     {
      "backup": {
       "exists": true,
       "immutable_copy": true,
       "last_tested_at": "2026-08-01T00:00:00Z",
       "rpo_hours": 1,
       "rto_hours": 4
      },
      "criticality": "critical",
      "name": "Core Banking Platform",
      "service_id": "svc-core-banking"
     }
    ],
    "unresolved_service_ids": [],
    "network": {
     "internet_facing": false,
     "open_ports": null,
     "segment_id": "data"
    },
    "edr": {
     "agent_healthy": true,
     "agent_installed": true,
     "detection_rules_active": [],
     "recent_alerts": []
    },
    "identity_access": {
     "mfa_enforced": false,
     "privileged_accounts_count": 1
    },
    "expected_annual_loss_inr": 30797931.688422706,
    "findings": [
     {
      "cve_id": "CVE-2026-31337",
      "epss_score": 0.34,
      "kev_listed": false,
      "remediated_at": null,
      "criticality": "high",
      "finding_id": "finding-0006",
      "first_seen_at": "2026-09-05T00:00:00Z",
      "provenance": {
       "connector": "nessus_connector",
       "raw_source_id": "x-6"
      },
      "type": "cve",
      "scenario": {
       "scenario_id": "asset-core-db-01::finding-0006",
       "description": "cve CVE-2026-31337 on asset-core-db-01 (internal_asset, critical-tier service impact); reached via attack graph: asset-web-01 72% (p=0.261), asset-vpn-01 28% (p=0.102)",
       "exposure_profile": "internal_asset",
       "threat_event_frequency": {
        "min": 2.1745200000000002,
        "most_likely": 4.3490400000000005,
        "max": 8.698080000000001
       },
       "exploit_probability": 0.34,
       "active_control_resistances": {
        "edr_active": 0.5
       },
       "vulnerability": 0.17,
       "graph_reachability_applied": true,
       "attack_routes": [
        {
         "entry_asset_id": "asset-web-01",
         "share": 0.7192207935544396,
         "reach_probability": 0.26066
        },
        {
         "entry_asset_id": "asset-vpn-01",
         "share": 0.28077920644556037,
         "reach_probability": 0.10176
        }
       ],
       "loss_event_frequency": {
        "min": 0.36966840000000006,
        "most_likely": 0.7393368000000001,
        "max": 1.4786736000000003
       },
       "criticality_tier": "critical",
       "backup_posture": "backup_tested_immutable",
       "loss_magnitude": {
        "min": 5000000.0,
        "most_likely": 20000000.0,
        "max": 80000000.0
       },
       "expected_annual_loss_inr": 23829231.23098278
      }
     },
     {
      "cve_id": null,
      "epss_score": null,
      "kev_listed": null,
      "remediated_at": null,
      "criticality": "high",
      "finding_id": "finding-0007",
      "first_seen_at": "2026-09-05T00:00:00Z",
      "provenance": {
       "connector": "nessus_connector",
       "raw_source_id": "x-7"
      },
      "type": "misconfiguration",
      "scenario": {
       "scenario_id": "asset-core-db-01::finding-0007",
       "description": "misconfiguration finding-0007 on asset-core-db-01 (internal_asset, critical-tier service impact); reached via attack graph: asset-web-01 72% (p=0.261), asset-vpn-01 28% (p=0.102)",
       "exposure_profile": "internal_asset",
       "threat_event_frequency": {
        "min": 2.1745200000000002,
        "most_likely": 4.3490400000000005,
        "max": 8.698080000000001
       },
       "exploit_probability": 0.1,
       "active_control_resistances": {
        "edr_active": 0.5
       },
       "vulnerability": 0.05,
       "graph_reachability_applied": true,
       "attack_routes": [
        {
         "entry_asset_id": "asset-web-01",
         "share": 0.7192207935544396,
         "reach_probability": 0.26066
        },
        {
         "entry_asset_id": "asset-vpn-01",
         "share": 0.28077920644556037,
         "reach_probability": 0.10176
        }
       ],
       "loss_event_frequency": {
        "min": 0.10872600000000002,
        "most_likely": 0.21745200000000003,
        "max": 0.43490400000000007
       },
       "criticality_tier": "critical",
       "backup_posture": "backup_tested_immutable",
       "loss_magnitude": {
        "min": 5000000.0,
        "most_likely": 20000000.0,
        "max": 80000000.0
       },
       "expected_annual_loss_inr": 6968700.457439926
      }
     }
    ]
   },
   {
    "asset_id": "asset-ad-01",
    "service_ids": [
     "svc-identity"
    ],
    "services": [
     {
      "backup": {
       "exists": true,
       "immutable_copy": false,
       "last_tested_at": "2026-08-01T00:00:00Z",
       "rpo_hours": 4,
       "rto_hours": 8
      },
      "criticality": "high",
      "name": "Directory & identity",
      "service_id": "svc-identity"
     }
    ],
    "unresolved_service_ids": [],
    "network": {
     "internet_facing": false,
     "open_ports": null,
     "segment_id": "corp"
    },
    "edr": {
     "agent_healthy": true,
     "agent_installed": true,
     "detection_rules_active": [],
     "recent_alerts": []
    },
    "identity_access": {
     "mfa_enforced": true,
     "privileged_accounts_count": 1
    },
    "expected_annual_loss_inr": 31789163.27731687,
    "findings": [
     {
      "cve_id": "CVE-2026-11002",
      "epss_score": 0.62,
      "kev_listed": true,
      "remediated_at": null,
      "criticality": "high",
      "finding_id": "finding-0008",
      "first_seen_at": "2026-09-05T00:00:00Z",
      "provenance": {
       "connector": "nessus_connector",
       "raw_source_id": "x-8"
      },
      "type": "cve",
      "scenario": {
       "scenario_id": "asset-ad-01::finding-0008",
       "description": "cve CVE-2026-11002 on asset-ad-01 (internal_asset, high-tier service impact); reached via attack graph: asset-web-01 58% (p=0.260), asset-vpn-01 42% (p=0.190)",
       "exposure_profile": "internal_asset",
       "threat_event_frequency": {
        "min": 7.692258064516127,
        "most_likely": 15.384516129032255,
        "max": 30.76903225806451
       },
       "exploit_probability": 0.62,
       "active_control_resistances": {
        "mfa_enforced": 0.4,
        "edr_active": 0.5
       },
       "vulnerability": 0.18600000000000003,
       "graph_reachability_applied": true,
       "attack_routes": [
        {
         "entry_asset_id": "asset-web-01",
         "share": 0.5782827159944862,
         "reach_probability": 0.2601
        },
        {
         "entry_asset_id": "asset-vpn-01",
         "share": 0.4217172840055138,
         "reach_probability": 0.18968
        }
       ],
       "loss_event_frequency": {
        "min": 1.4307599999999998,
        "most_likely": 2.8615199999999996,
        "max": 5.723039999999999
       },
       "criticality_tier": "high",
       "backup_posture": "backup_tested_no_immutable",
       "loss_magnitude": {
        "min": 1300000.0,
        "most_likely": 6500000.0,
        "max": 26000000.0
       },
       "expected_annual_loss_inr": 31789163.27731687
      }
     }
    ]
   },
   {
    "asset_id": "asset-jump-01",
    "service_ids": [
     "svc-identity"
    ],
    "services": [
     {
      "backup": {
       "exists": true,
       "immutable_copy": false,
       "last_tested_at": "2026-08-01T00:00:00Z",
       "rpo_hours": 4,
       "rto_hours": 8
      },
      "criticality": "high",
      "name": "Directory & identity",
      "service_id": "svc-identity"
     }
    ],
    "unresolved_service_ids": [],
    "network": {
     "internet_facing": false,
     "open_ports": null,
     "segment_id": "mgmt"
    },
    "edr": {
     "agent_healthy": true,
     "agent_installed": true,
     "detection_rules_active": [],
     "recent_alerts": []
    },
    "identity_access": {
     "mfa_enforced": true,
     "privileged_accounts_count": 1
    },
    "expected_annual_loss_inr": null,
    "findings": []
   },
   {
    "asset_id": "asset-ftp-legacy",
    "service_ids": [
     "svc-legacy"
    ],
    "services": [
     {
      "backup": {
       "exists": true,
       "immutable_copy": false,
       "last_tested_at": null,
       "rpo_hours": 4,
       "rto_hours": 8
      },
      "criticality": "medium",
      "name": "Legacy file transfer",
      "service_id": "svc-legacy"
     }
    ],
    "unresolved_service_ids": [],
    "network": {
     "internet_facing": false,
     "open_ports": null,
     "segment_id": null
    },
    "edr": {
     "agent_healthy": null,
     "agent_installed": false,
     "detection_rules_active": null,
     "recent_alerts": null
    },
    "identity_access": {
     "mfa_enforced": false,
     "privileged_accounts_count": 1
    },
    "expected_annual_loss_inr": 3790360.751900925,
    "findings": [
     {
      "cve_id": "CVE-2019-99999",
      "epss_score": 0.55,
      "kev_listed": true,
      "remediated_at": null,
      "criticality": "high",
      "finding_id": "finding-0009",
      "first_seen_at": "2026-09-05T00:00:00Z",
      "provenance": {
       "connector": "nessus_connector",
       "raw_source_id": "x-9"
      },
      "type": "cve",
      "scenario": {
       "scenario_id": "asset-ftp-legacy::finding-0009",
       "description": "cve CVE-2019-99999 on asset-ftp-legacy (internal_asset, medium-tier service impact)",
       "exposure_profile": "internal_asset",
       "threat_event_frequency": {
        "min": 1.0,
        "most_likely": 2.0,
        "max": 6.0
       },
       "exploit_probability": 0.55,
       "active_control_resistances": {},
       "vulnerability": 0.55,
       "graph_reachability_applied": false,
       "attack_routes": [],
       "loss_event_frequency": {
        "min": 0.55,
        "most_likely": 1.1,
        "max": 3.3000000000000003
       },
       "criticality_tier": "medium",
       "backup_posture": "backup_untested",
       "loss_magnitude": {
        "min": 360000.0,
        "most_likely": 1800000.0,
        "max": 9000000.0
       },
       "expected_annual_loss_inr": 3790360.751900925
      }
     }
    ]
   }
  ]
 },
 "targets": {
  "asset-web-01": {
   "snapshot_id": "sha256:6c5479ef11fbe2cea37c201cb892cd3c976b94aa98491df3600565fa5e728cbf",
   "asset_id": "asset-web-01",
   "samples": 50000,
   "included_asset_ids": [
    "asset-vpn-01",
    "asset-web-01"
   ],
   "compromise_probability": 0.25964,
   "node_probabilities": {
    "asset-web-01": 0.25964,
    "asset-vpn-01": 0.1858
   },
   "reached_probabilities": {
    "asset-web-01": 1.0,
    "asset-vpn-01": 1.0
   },
   "edges": [
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-vpn-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-web-01",
     "reason": "same_segment:dmz"
    }
   ]
  },
  "asset-hr-db-01": {
   "snapshot_id": "sha256:6c5479ef11fbe2cea37c201cb892cd3c976b94aa98491df3600565fa5e728cbf",
   "asset_id": "asset-hr-db-01",
   "samples": 50000,
   "included_asset_ids": [
    "asset-ad-01",
    "asset-hr-db-01",
    "asset-vpn-01",
    "asset-web-01"
   ],
   "compromise_probability": 0.01972,
   "node_probabilities": {
    "asset-hr-db-01": 0.01972,
    "asset-ad-01": 0.18494,
    "asset-web-01": 0.26378,
    "asset-vpn-01": 0.18494
   },
   "reached_probabilities": {
    "asset-hr-db-01": 0.4004,
    "asset-ad-01": 0.4004,
    "asset-web-01": 1.0,
    "asset-vpn-01": 1.0
   },
   "edges": [
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-vpn-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-web-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-hr-db-01",
     "target_asset_id": "asset-ad-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-ad-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    }
   ]
  },
  "asset-vpn-01": {
   "snapshot_id": "sha256:6c5479ef11fbe2cea37c201cb892cd3c976b94aa98491df3600565fa5e728cbf",
   "asset_id": "asset-vpn-01",
   "samples": 50000,
   "included_asset_ids": [
    "asset-vpn-01",
    "asset-web-01"
   ],
   "compromise_probability": 0.18716,
   "node_probabilities": {
    "asset-web-01": 0.26118,
    "asset-vpn-01": 0.18716
   },
   "reached_probabilities": {
    "asset-web-01": 1.0,
    "asset-vpn-01": 1.0
   },
   "edges": [
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-vpn-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-web-01",
     "reason": "same_segment:dmz"
    }
   ]
  },
  "asset-api-01": {
   "snapshot_id": "sha256:6c5479ef11fbe2cea37c201cb892cd3c976b94aa98491df3600565fa5e728cbf",
   "asset_id": "asset-api-01",
   "samples": 50000,
   "included_asset_ids": [
    "asset-ad-01",
    "asset-api-01",
    "asset-hr-db-01",
    "asset-jump-01",
    "asset-loan-app-01",
    "asset-vpn-01",
    "asset-web-01"
   ],
   "compromise_probability": 0.31004,
   "node_probabilities": {
    "asset-api-01": 0.31004,
    "asset-jump-01": 0.0,
    "asset-vpn-01": 0.18552,
    "asset-loan-app-01": 0.02558,
    "asset-hr-db-01": 0.01856,
    "asset-ad-01": 0.18552,
    "asset-web-01": 0.26232
   },
   "reached_probabilities": {
    "asset-api-01": 0.3988,
    "asset-jump-01": 0.1959,
    "asset-vpn-01": 1.0,
    "asset-loan-app-01": 0.3988,
    "asset-hr-db-01": 0.3988,
    "asset-ad-01": 0.3988,
    "asset-web-01": 1.0
   },
   "edges": [
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-vpn-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-web-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-hr-db-01",
     "target_asset_id": "asset-ad-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-ad-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-api-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "same_segment:app"
    },
    {
     "source_asset_id": "asset-loan-app-01",
     "target_asset_id": "asset-api-01",
     "reason": "same_segment:app"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-api-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-api-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-hr-db-01",
     "target_asset_id": "asset-jump-01",
     "reason": "segment_reachability:corp->mgmt"
    },
    {
     "source_asset_id": "asset-ad-01",
     "target_asset_id": "asset-jump-01",
     "reason": "segment_reachability:corp->mgmt"
    },
    {
     "source_asset_id": "asset-jump-01",
     "target_asset_id": "asset-api-01",
     "reason": "segment_reachability:mgmt->app"
    },
    {
     "source_asset_id": "asset-jump-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "segment_reachability:mgmt->app"
    }
   ]
  },
  "asset-loan-app-01": {
   "snapshot_id": "sha256:6c5479ef11fbe2cea37c201cb892cd3c976b94aa98491df3600565fa5e728cbf",
   "asset_id": "asset-loan-app-01",
   "samples": 50000,
   "included_asset_ids": [
    "asset-ad-01",
    "asset-api-01",
    "asset-hr-db-01",
    "asset-jump-01",
    "asset-loan-app-01",
    "asset-vpn-01",
    "asset-web-01"
   ],
   "compromise_probability": 0.02406,
   "node_probabilities": {
    "asset-api-01": 0.30908,
    "asset-jump-01": 0.0,
    "asset-vpn-01": 0.18454,
    "asset-loan-app-01": 0.02406,
    "asset-hr-db-01": 0.0208,
    "asset-ad-01": 0.18454,
    "asset-web-01": 0.26198
   },
   "reached_probabilities": {
    "asset-api-01": 0.39818,
    "asset-jump-01": 0.19602,
    "asset-vpn-01": 1.0,
    "asset-loan-app-01": 0.39818,
    "asset-hr-db-01": 0.39818,
    "asset-ad-01": 0.39818,
    "asset-web-01": 1.0
   },
   "edges": [
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-vpn-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-web-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-hr-db-01",
     "target_asset_id": "asset-ad-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-ad-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-api-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "same_segment:app"
    },
    {
     "source_asset_id": "asset-loan-app-01",
     "target_asset_id": "asset-api-01",
     "reason": "same_segment:app"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-api-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-api-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-hr-db-01",
     "target_asset_id": "asset-jump-01",
     "reason": "segment_reachability:corp->mgmt"
    },
    {
     "source_asset_id": "asset-ad-01",
     "target_asset_id": "asset-jump-01",
     "reason": "segment_reachability:corp->mgmt"
    },
    {
     "source_asset_id": "asset-jump-01",
     "target_asset_id": "asset-api-01",
     "reason": "segment_reachability:mgmt->app"
    },
    {
     "source_asset_id": "asset-jump-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "segment_reachability:mgmt->app"
    }
   ]
  },
  "asset-core-db-01": {
   "snapshot_id": "sha256:6c5479ef11fbe2cea37c201cb892cd3c976b94aa98491df3600565fa5e728cbf",
   "asset_id": "asset-core-db-01",
   "samples": 50000,
   "included_asset_ids": [
    "asset-ad-01",
    "asset-api-01",
    "asset-core-db-01",
    "asset-hr-db-01",
    "asset-jump-01",
    "asset-loan-app-01",
    "asset-vpn-01",
    "asset-web-01"
   ],
   "compromise_probability": 0.066,
   "node_probabilities": {
    "asset-core-db-01": 0.066,
    "asset-loan-app-01": 0.0252,
    "asset-ad-01": 0.18516,
    "asset-api-01": 0.30932,
    "asset-jump-01": 0.0,
    "asset-vpn-01": 0.18516,
    "asset-hr-db-01": 0.0203,
    "asset-web-01": 0.26066
   },
   "reached_probabilities": {
    "asset-core-db-01": 0.31508,
    "asset-loan-app-01": 0.39848,
    "asset-ad-01": 0.39848,
    "asset-api-01": 0.39848,
    "asset-jump-01": 0.19644,
    "asset-vpn-01": 1.0,
    "asset-hr-db-01": 0.39848,
    "asset-web-01": 1.0
   },
   "edges": [
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-vpn-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-web-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-hr-db-01",
     "target_asset_id": "asset-ad-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-ad-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-api-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "same_segment:app"
    },
    {
     "source_asset_id": "asset-loan-app-01",
     "target_asset_id": "asset-api-01",
     "reason": "same_segment:app"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-api-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-api-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "segment_reachability:dmz->app"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-api-01",
     "target_asset_id": "asset-core-db-01",
     "reason": "segment_reachability:app->data"
    },
    {
     "source_asset_id": "asset-loan-app-01",
     "target_asset_id": "asset-core-db-01",
     "reason": "segment_reachability:app->data"
    },
    {
     "source_asset_id": "asset-hr-db-01",
     "target_asset_id": "asset-jump-01",
     "reason": "segment_reachability:corp->mgmt"
    },
    {
     "source_asset_id": "asset-ad-01",
     "target_asset_id": "asset-jump-01",
     "reason": "segment_reachability:corp->mgmt"
    },
    {
     "source_asset_id": "asset-jump-01",
     "target_asset_id": "asset-core-db-01",
     "reason": "segment_reachability:mgmt->data"
    },
    {
     "source_asset_id": "asset-jump-01",
     "target_asset_id": "asset-api-01",
     "reason": "segment_reachability:mgmt->app"
    },
    {
     "source_asset_id": "asset-jump-01",
     "target_asset_id": "asset-loan-app-01",
     "reason": "segment_reachability:mgmt->app"
    }
   ]
  },
  "asset-ad-01": {
   "snapshot_id": "sha256:6c5479ef11fbe2cea37c201cb892cd3c976b94aa98491df3600565fa5e728cbf",
   "asset_id": "asset-ad-01",
   "samples": 50000,
   "included_asset_ids": [
    "asset-ad-01",
    "asset-hr-db-01",
    "asset-vpn-01",
    "asset-web-01"
   ],
   "compromise_probability": 0.18968,
   "node_probabilities": {
    "asset-hr-db-01": 0.01926,
    "asset-ad-01": 0.18968,
    "asset-web-01": 0.2601,
    "asset-vpn-01": 0.18968
   },
   "reached_probabilities": {
    "asset-hr-db-01": 0.401,
    "asset-ad-01": 0.401,
    "asset-web-01": 1.0,
    "asset-vpn-01": 1.0
   },
   "edges": [
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-vpn-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-web-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-hr-db-01",
     "target_asset_id": "asset-ad-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-ad-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    }
   ]
  },
  "asset-jump-01": {
   "snapshot_id": "sha256:6c5479ef11fbe2cea37c201cb892cd3c976b94aa98491df3600565fa5e728cbf",
   "asset_id": "asset-jump-01",
   "samples": 50000,
   "included_asset_ids": [
    "asset-ad-01",
    "asset-hr-db-01",
    "asset-jump-01",
    "asset-vpn-01",
    "asset-web-01"
   ],
   "compromise_probability": 0.0,
   "node_probabilities": {
    "asset-jump-01": 0.0,
    "asset-vpn-01": 0.18614,
    "asset-hr-db-01": 0.01994,
    "asset-ad-01": 0.18614,
    "asset-web-01": 0.2603
   },
   "reached_probabilities": {
    "asset-jump-01": 0.19646,
    "asset-vpn-01": 1.0,
    "asset-hr-db-01": 0.39794,
    "asset-ad-01": 0.39794,
    "asset-web-01": 1.0
   },
   "edges": [
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-vpn-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-web-01",
     "reason": "same_segment:dmz"
    },
    {
     "source_asset_id": "asset-hr-db-01",
     "target_asset_id": "asset-ad-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-ad-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "same_segment:corp"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-web-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-hr-db-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-vpn-01",
     "target_asset_id": "asset-ad-01",
     "reason": "segment_reachability:dmz->corp"
    },
    {
     "source_asset_id": "asset-hr-db-01",
     "target_asset_id": "asset-jump-01",
     "reason": "segment_reachability:corp->mgmt"
    },
    {
     "source_asset_id": "asset-ad-01",
     "target_asset_id": "asset-jump-01",
     "reason": "segment_reachability:corp->mgmt"
    }
   ]
  }
 }
};
