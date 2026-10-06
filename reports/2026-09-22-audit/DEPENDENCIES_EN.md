# Kedrogy dependency audit appendix

Audit date: 22 September 2026. The installed frontend npm dependencies and public packages in mysite/.venv and example/.venv were checked. Project packages, licensed Prodigy/ysz packages and dependencies installed directly from Git or local paths were not submitted to the Python scanner. Dependencies were not changed during this check.

## Interpretation rules

These are advisory-database results, not confirmed attacks against the application. Applicability depends on the functions used, execution mode, operating system and whether an attacker can reach the relevant input. The Python environments overlap; their counts must not be added as unique project-wide vulnerabilities. Repeated advisory IDs in the source JSON are deduplicated by package and ID. Different IDs can also describe related problems, so the number of IDs does not represent independent attacks.

Fix versions reproduce scanner data and are not ready-to-run upgrade instructions. A fix from another Django release branch or a Transformers major upgrade may be incompatible with this project. Each selected upgrade needs a new lockfile, build, tests and another scan.

## npm

npm audit summary: {"info": 0, "low": 3, "moderate": 1, "high": 7, "critical": 0, "total": 11}.

| Package | Installed version | Scanner severity | Direct dependency | Advisory |
|---|---|---|---|---|
| @babel/core | 7.29.0 | low | no | [GHSA-4x5r-pxfx-6jf8](https://github.com/advisories/GHSA-4x5r-pxfx-6jf8) |
| baseline-browser-mapping | 2.10.27 | moderate | no | [GHSA-w5vr-8v7q-w6rv](https://github.com/advisories/GHSA-w5vr-8v7q-w6rv) |
| brace-expansion | 1.1.14 | high | no | [GHSA-jxxr-4gwj-5jf2](https://github.com/advisories/GHSA-jxxr-4gwj-5jf2); [GHSA-3jxr-9vmj-r5cp](https://github.com/advisories/GHSA-3jxr-9vmj-r5cp); [GHSA-mh99-v99m-4gvg](https://github.com/advisories/GHSA-mh99-v99m-4gvg); [GHSA-rgw5-rvv9-x895](https://github.com/advisories/GHSA-rgw5-rvv9-x895) |
| browserslist | 4.28.2 | high | no | [GHSA-c83g-rgw3-j3cx](https://github.com/advisories/GHSA-c83g-rgw3-j3cx); [GHSA-73wf-gq98-2v4g](https://github.com/advisories/GHSA-73wf-gq98-2v4g) |
| esbuild | 0.27.7 | low | no | [GHSA-g7r4-m6w7-qqqr](https://github.com/advisories/GHSA-g7r4-m6w7-qqqr) |
| js-yaml | 4.1.1 | high | no | [GHSA-h67p-54hq-rp68](https://github.com/advisories/GHSA-h67p-54hq-rp68); [GHSA-52cp-r559-cp3m](https://github.com/advisories/GHSA-52cp-r559-cp3m); [GHSA-5p4m-2wfm-xmqj](https://github.com/advisories/GHSA-5p4m-2wfm-xmqj); [GHSA-2883-xcg3-v3hh](https://github.com/advisories/GHSA-2883-xcg3-v3hh) |
| nanoid | 3.3.12 | high | no | [GHSA-28wg-ghj8-5hjv](https://github.com/advisories/GHSA-28wg-ghj8-5hjv); [GHSA-2v37-7h3g-55p8](https://github.com/advisories/GHSA-2v37-7h3g-55p8) |
| postcss | 8.5.14 | high | no | [GHSA-fxqj-rqcc-2cmp](https://github.com/advisories/GHSA-fxqj-rqcc-2cmp); [GHSA-r28c-9q8g-f849](https://github.com/advisories/GHSA-r28c-9q8g-f849) |
| react-router | 7.15.0 | high | yes | [GHSA-84g9-w2xq-vcv6](https://github.com/advisories/GHSA-84g9-w2xq-vcv6); [GHSA-wrjc-x8rr-h8h6](https://github.com/advisories/GHSA-wrjc-x8rr-h8h6); [GHSA-h8fp-f39c-q6mh](https://github.com/advisories/GHSA-h8fp-f39c-q6mh); [GHSA-337j-9hxr-rhxg](https://github.com/advisories/GHSA-337j-9hxr-rhxg); [GHSA-chx6-hx7r-mcp5](https://github.com/advisories/GHSA-chx6-hx7r-mcp5); [GHSA-qwww-vcr4-c8h2](https://github.com/advisories/GHSA-qwww-vcr4-c8h2) |
| react-router-dom | 7.15.0 | low | yes | through react-router |
| vite | 7.3.2 | high | yes | [GHSA-v6wh-96g9-6wx3](https://github.com/advisories/GHSA-v6wh-96g9-6wx3); [GHSA-fx2h-pf6j-xcff](https://github.com/advisories/GHSA-fx2h-pf6j-xcff) |

Some Vite/esbuild advisories concern Windows; some React Router advisories concern server, SSR or RSC modes. The checked application uses a BrowserRouter SPA, so those conditions cannot automatically be assumed. Client navigation and handled URLs need separate applicability checks. Build dependencies also need updates, but their exposure differs from the runtime API.

## Python backend

68 public packages checked; 10 affected packages and 38 unique package/advisory-ID pairs. The raw output contains 67 advisory rows, including duplicates.

| Package | Version | Unique IDs | ID | Fix versions reported by scanner |
|---|---|---|---|---|
| anyio | 4.13.0 | 2 | CVE-2026-63374, CVE-2026-64847 | 4.14.2 |
| click | 8.3.2 | 1 | PYSEC-2026-2132 | 8.3.3 |
| django | 6.0.4 | 12 | PYSEC-2026-197, PYSEC-2026-198, PYSEC-2026-199, PYSEC-2026-200, PYSEC-2026-201, PYSEC-2026-2090, PYSEC-2026-2091, PYSEC-2026-2092, PYSEC-2026-3717, PYSEC-2026-50, PYSEC-2026-54, PYSEC-2026-55 | 5.2.14, 5.2.15, 5.2.16, 5.2.17, 6.0.5, 6.0.6, 6.0.7, 6.0.8 |
| djangorestframework | 3.17.1 | 2 | PYSEC-2026-3827, PYSEC-2026-3828 | 3.17.2 |
| idna | 3.11 | 1 | PYSEC-2026-215 | 3.15 |
| pyjwt | 2.12.1 | 5 | PYSEC-2026-175, PYSEC-2026-176, PYSEC-2026-177, PYSEC-2026-178, PYSEC-2026-179 | 2.13.0 |
| setuptools | 82.0.1 | 1 | PYSEC-2026-3447 | 83.0.0 |
| sqlparse | 0.5.5 | 5 | PYSEC-2026-3696, PYSEC-2026-3697, PYSEC-2026-3698, PYSEC-2026-3699, PYSEC-2026-3923 | 0.6.0 |
| starlette | 0.46.2 | 7 | PYSEC-2026-161, PYSEC-2026-1941, PYSEC-2026-1942, PYSEC-2026-2280, PYSEC-2026-2281, PYSEC-2026-248, PYSEC-2026-249 | 0.47.2, 0.49.1, 1.0.1, 1.1.0, 1.3.0, 1.3.1 |
| urllib3 | 2.6.3 | 2 | PYSEC-2026-141, PYSEC-2026-142 | 2.7.0 |

## Python ML

209 public packages checked; 27 affected packages and 116 unique package/advisory-ID pairs. The raw output contains 197 advisory rows, including duplicates.

| Package | Version | Unique IDs | ID | Fix versions reported by scanner |
|---|---|---|---|---|
| accelerate | 1.12.0 | 1 | PYSEC-2026-3804 | not supplied |
| aiohttp | 3.13.3 | 24 | PYSEC-2026-2094, PYSEC-2026-2095, PYSEC-2026-2096, PYSEC-2026-2097, PYSEC-2026-2098, PYSEC-2026-2099, PYSEC-2026-2100, PYSEC-2026-2101, PYSEC-2026-2102, PYSEC-2026-2103, PYSEC-2026-2104, PYSEC-2026-2105, PYSEC-2026-2106, PYSEC-2026-2107, PYSEC-2026-2108, PYSEC-2026-2109, PYSEC-2026-2110, PYSEC-2026-2111, PYSEC-2026-2112, PYSEC-2026-2113, PYSEC-2026-237, PYSEC-2026-3545, PYSEC-2026-3546, PYSEC-2026-3547 | 3.13.4, 3.14.0, 3.14.1, 3.14.2, 3.14.3 |
| anyio | 4.12.1 | 2 | CVE-2026-63374, CVE-2026-64847 | 4.14.2 |
| click | 8.3.1 | 1 | PYSEC-2026-2132 | 8.3.3 |
| cryptography | 46.0.4 | 7 | GHSA-537c-gmf6-5ccf, PYSEC-2026-2141, PYSEC-2026-35, PYSEC-2026-3552, PYSEC-2026-3553, PYSEC-2026-3554, PYSEC-2026-36 | 46.0.5, 46.0.6, 46.0.7, 48.0.1, 49.0.0, 50.0.0 |
| datasets | 4.5.0 | 1 | PYSEC-2026-3716 | 5.0.1 |
| dynaconf | 3.2.12 | 1 | PYSEC-2026-2147 | 3.2.13 |
| gitpython | 3.1.46 | 28 | CVE-2026-73624, PYSEC-2026-2160, PYSEC-2026-2161, PYSEC-2026-2162, PYSEC-2026-2163, PYSEC-2026-3783, PYSEC-2026-3784, PYSEC-2026-3785, PYSEC-2026-3786, PYSEC-2026-3787, PYSEC-2026-3788, PYSEC-2026-3836, PYSEC-2026-3837, PYSEC-2026-3838, PYSEC-2026-3839, PYSEC-2026-3840, PYSEC-2026-3841, PYSEC-2026-3843, PYSEC-2026-3948, PYSEC-2026-3949, PYSEC-2026-3950, PYSEC-2026-3951, PYSEC-2026-3952, PYSEC-2026-3953, PYSEC-2026-3980, PYSEC-2026-3981, PYSEC-2026-3982, PYSEC-2026-3984 | 3.1.47, 3.1.48, 3.1.49, 3.1.50, 3.1.51, 3.1.53, 3.1.54, 3.1.55, 3.1.56, 3.1.57, 3.1.58, 3.1.59, 3.1.60 |
| idna | 3.11 | 1 | PYSEC-2026-215 | 3.15 |
| kedro | 1.2.0 | 1 | PYSEC-2026-72 | 1.3.0 |
| kedro-datasets | 9.1.1 | 1 | PYSEC-2026-2545 | 9.3.0 |
| lxml | 4.9.4 | 1 | PYSEC-2026-87 | 6.1.0 |
| msgpack | 1.1.2 | 1 | PYSEC-2026-3625 | 1.2.1 |
| pyarrow | 23.0.0 | 1 | PYSEC-2026-113 | 23.0.1 |
| pyasn1 | 0.6.2 | 4 | PYSEC-2026-2263, PYSEC-2026-3455, PYSEC-2026-3456, PYSEC-2026-3457 | 0.6.3, 0.6.4 |
| pygments | 2.19.2 | 1 | PYSEC-2026-2987 | 2.20.0 |
| pyjwt | 2.11.0 | 6 | PYSEC-2026-120, PYSEC-2026-175, PYSEC-2026-176, PYSEC-2026-177, PYSEC-2026-178, PYSEC-2026-179 | 2.12.0, 2.12.1, 2.13.0 |
| python-dotenv | 1.2.1 | 1 | PYSEC-2026-2270 | 1.2.2 |
| python-multipart | 0.0.22 | 5 | PYSEC-2026-3036, PYSEC-2026-3037, PYSEC-2026-3038, PYSEC-2026-3039, PYSEC-2026-3040 | 0.0.26, 0.0.27, 0.0.30, 0.0.31 |
| requests | 2.32.5 | 1 | PYSEC-2026-2275 | 2.33.0 |
| setuptools | 82.0.0 | 1 | PYSEC-2026-3447 | 83.0.0 |
| starlette | 0.46.2 | 7 | PYSEC-2026-161, PYSEC-2026-1941, PYSEC-2026-1942, PYSEC-2026-2280, PYSEC-2026-2281, PYSEC-2026-248, PYSEC-2026-249 | 0.47.2, 0.49.1, 1.0.1, 1.1.0, 1.3.0, 1.3.1 |
| torch | 2.10.0 | 2 | PYSEC-2025-194, PYSEC-2026-139 | 2.13.0 |
| tornado | 6.5.4 | 8 | GHSA-8423-8fgw-73vq, GHSA-pw6j-qg29-8w7f, PYSEC-2026-140, PYSEC-2026-2287, PYSEC-2026-3387, PYSEC-2026-3388, PYSEC-2026-3389, PYSEC-2026-3928 | 6.5.5, 6.5.6, 6.5.7, 6.5.8 |
| transformers | 4.57.1 | 6 | PYSEC-2025-217, PYSEC-2025-218, PYSEC-2026-2288, PYSEC-2026-2289, PYSEC-2026-2290, PYSEC-2026-3929 | 5.0.0, 5.0.0rc3, 5.10.0, 5.3.0, 5.5.0 |
| urllib3 | 2.6.3 | 2 | PYSEC-2026-141, PYSEC-2026-142 | 2.7.0 |
| werkzeug | 3.1.5 | 1 | PYSEC-2026-2320 | 3.1.6 |

## Recommended order of work

1. First fix the application's SQL/YAML injection paths, missing authorization and secret exposure. Library upgrades do not resolve those defects.
2. Upgrade compatible security releases for the web runtime and network libraries; check Django, DRF and Prodigy constraints.
3. Upgrade the frontend runtime and development toolchain, then run build, lint and browser checks.
4. Separately verify compatibility among Transformers, Torch, Datasets and Accelerate, including existing checkpoint formats. Preserve working artifacts before upgrading.
5. Rebuild images, verify their actual installed versions and rescan. A local virtual environment does not prove which library version is inside an older image.
6. Record justified exceptions with the exact advisory, unreachable function or mode, applied protection and review date.

Project packages and secrets were neither upgraded nor published. Repeat checks with npm audit and pip-audit against prepared pinned requirements for public packages. These results are limited to the snapshot date.
