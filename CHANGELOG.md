# Changelog

## [3.6.5](https://github.com/tomag-9/zdravy-projekt/compare/v3.6.4...v3.6.5) (2026-09-11)


### Bug Fixes

* **edupage:** trvalo umlčať false-positive olovrant attention flagy ([0ac66db](https://github.com/tomag-9/zdravy-projekt/commit/0ac66dba1ab13faa8b854257912f90c145c60862))
* **edupage:** zachovať kompletné diétne kombinácie ([3d68d04](https://github.com/tomag-9/zdravy-projekt/commit/3d68d0461db773fa057e0c91efde59ff1fbc990e))
* **tests:** opraviť zabudnutú duplicitnú asserciu na dsbNNN SJ diétu ([89f8dac](https://github.com/tomag-9/zdravy-projekt/commit/89f8daccc9e0c3554b3be8b24164780ee4946432))

## [3.6.4](https://github.com/tomag-9/zdravy-projekt/compare/v3.6.3...v3.6.4) (2026-09-11)


### Bug Fixes

* **edupage:** potvrdiť viditeľné kombinované diéty ([#647](https://github.com/tomag-9/zdravy-projekt/issues/647)) ([4ebb8c3](https://github.com/tomag-9/zdravy-projekt/commit/4ebb8c31ba6a4b44072fecf34b0a51ec00374f5b))

## [3.6.3](https://github.com/tomag-9/zdravy-projekt/compare/v3.6.2...v3.6.3) (2026-09-11)


### Bug Fixes

* **ci:** zoradiť EduPage importy ([416fe15](https://github.com/tomag-9/zdravy-projekt/commit/416fe15f9a06a0805254dfb0010832487291c4c0))
* **edupage:** deklarovať kontext scrapera ([7c9c000](https://github.com/tomag-9/zdravy-projekt/commit/7c9c000e4100ba6148f9e3ea28c4ab1991078ba4))
* **edupage:** rešpektovať viditeľné diéty prevádzky ([8ee7d11](https://github.com/tomag-9/zdravy-projekt/commit/8ee7d1136fc29aa314b41f751a594659f4bdddd9))
* **edupage:** rešpektovať viditeľné diéty prevádzky ([#645](https://github.com/tomag-9/zdravy-projekt/issues/645)) ([3a677e7](https://github.com/tomag-9/zdravy-projekt/commit/3a677e7cd6dca089fb8e4cffccd0ad39054aaf89))
* **edupage:** zachovať kompatibilitu scrape testov ([4bd63cf](https://github.com/tomag-9/zdravy-projekt/commit/4bd63cfbbffced639030937ecf603e3c87ded7f9))

## [3.6.2](https://github.com/tomag-9/zdravy-projekt/compare/v3.6.1...v3.6.2) (2026-09-11)


### Bug Fixes

* **diety:** bezpečne prepojiť potvrdené duplicity ([f79b5e9](https://github.com/tomag-9/zdravy-projekt/commit/f79b5e97a534484fb9b947932feb8efb6229647e))
* **diety:** bezpečne prepojiť potvrdené duplicity ([#643](https://github.com/tomag-9/zdravy-projekt/issues/643)) ([3f858aa](https://github.com/tomag-9/zdravy-projekt/commit/3f858aa5fc20826620a35820700543eb6784c690))

## [3.6.1](https://github.com/tomag-9/zdravy-projekt/compare/v3.6.0...v3.6.1) (2026-09-11)


### Bug Fixes

* **trasy:** oprav 0113, ktorá raňajky/olovrant nasmerovala na obedovú trasu ([56307dd](https://github.com/tomag-9/zdravy-projekt/commit/56307dd6f5e960252cefc974b5ad0910e1ae6942))

## [3.6.0](https://github.com/tomag-9/zdravy-projekt/compare/v3.5.1...v3.6.0) (2026-09-11)


### Features

* **diety:** polievka samostatná zložka v diet-component-merge boarde ([0b6f97f](https://github.com/tomag-9/zdravy-projekt/commit/0b6f97f8272c84aee92d6d557a0343d07c1aee7b))
* samostatné trasy a tabuľky pre raňajky/obed/olovrant (redo, zmergované s [#568](https://github.com/tomag-9/zdravy-projekt/issues/568)) ([#630](https://github.com/tomag-9/zdravy-projekt/issues/630)) ([4648c2e](https://github.com/tomag-9/zdravy-projekt/commit/4648c2e075ba72ec03a7eee835b99a1dad3349c9))


### Bug Fixes

* **objednavky:** align client order state with automation ([7b7e3d5](https://github.com/tomag-9/zdravy-projekt/commit/7b7e3d5e6f0907179d593ad553f904ea293dad9c))
* **objednavky:** auto-order nesmie prepísať explicitne vynulovaný chod ([ada26cf](https://github.com/tomag-9/zdravy-projekt/commit/ada26cf6647dc5383f8c1ba1929afa596096a787))
* **objednavky:** complete concurrent scoped auto-orders ([2cb0c36](https://github.com/tomag-9/zdravy-projekt/commit/2cb0c3669e9ca3b846c6003555c543dc3029991e))
* **objednavky:** N+1 v predikcii a prepis nedotknutého draftu prázdnym GET ([2b57586](https://github.com/tomag-9/zdravy-projekt/commit/2b57586d81c059e4947f539ace4ea68b76fa67dd))
* **objednavky:** serialize auto-order and explicit resets ([c2bc418](https://github.com/tomag-9/zdravy-projekt/commit/c2bc418adad55d61725cd8f81aedcfe034da486b))
* **trasy:** backfill meal routes from lunch ([a60ee36](https://github.com/tomag-9/zdravy-projekt/commit/a60ee36258e7f281f9e1faa7db4f6f31db83811b))

## [3.5.1](https://github.com/tomag-9/zdravy-projekt/compare/v3.5.0...v3.5.1) (2026-09-11)


### Bug Fixes

* **objednavky:** kategória menu neobmedzuje, len visible_menus prevádzky ([#636](https://github.com/tomag-9/zdravy-projekt/issues/636)) ([bda7dee](https://github.com/tomag-9/zdravy-projekt/commit/bda7dee0122b8fb39a42c8fa2b4779a4721ed7bd))

## [3.5.0](https://github.com/tomag-9/zdravy-projekt/compare/v3.4.0...v3.5.0) (2026-09-11)


### Features

* **admin:** checkbox pre menu_bc_same_deadline_as_lunch v nastaveniach prevádzky ([33bf27a](https://github.com/tomag-9/zdravy-projekt/commit/33bf27a8966ee2fd16b8769830e31eebd52bdf48))


### Bug Fixes

* **diety:** dry-run náhľad fix_combined_diet_base_links_2026_09 hlásil zavádzajúce 'založím novú diétu' ([7c59e8e](https://github.com/tomag-9/zdravy-projekt/commit/7c59e8ec784941c3386eb8a3fa31884616fdf7b8))

## [3.4.0](https://github.com/tomag-9/zdravy-projekt/compare/v3.3.1...v3.4.0) (2026-09-10)


### Features

* **objednavky:** per-prevádzka výnimka z prísneho 2-dňového Menu B/C termínu ([ff0ec78](https://github.com/tomag-9/zdravy-projekt/commit/ff0ec781f2cea3fb4681ca65bff55d7993ad9509))


### Bug Fixes

* **diety:** base_diets pre 2 kombinácie z 10.9.2026 + Diet.name limit 100→255 ([3f2f29b](https://github.com/tomag-9/zdravy-projekt/commit/3f2f29b900883641d0a65432565a8d8c1611d979))
* **diety:** diéta [#2](https://github.com/tomag-9/zdravy-projekt/issues/2) sa má naviazať na existujúce id=46 pod starým menom, nie duplikovať ([d9e2fd7](https://github.com/tomag-9/zdravy-projekt/commit/d9e2fd733726474583bc26448ed4ad936733b7ca))
* **edupage:** Školička – učiteľ/žiak s diétou v stĺpci Menu B/C sa počíta ako B/C, nie ako diéta ([3382752](https://github.com/tomag-9/zdravy-projekt/commit/3382752a95e2096f90260e3f9da2a8d6f8ecfd0c))

## [3.3.1](https://github.com/tomag-9/zdravy-projekt/compare/v3.3.0...v3.3.1) (2026-09-10)


### Bug Fixes

* **gramage:** dlhý názov diéty sa v PDF nerozpadal na písmená, S/Z odznak správnu výšku ([#627](https://github.com/tomag-9/zdravy-projekt/issues/627)) ([711d222](https://github.com/tomag-9/zdravy-projekt/commit/711d2228490e998b5187181157c3fe61e23150f1))

## [3.3.0](https://github.com/tomag-9/zdravy-projekt/compare/v3.2.3...v3.3.0) (2026-09-10)


### Features

* **gramage:** diet-component-merge default "spolu", "Zabaliť spolu:" per prevádzka, S/Z odznak ([11fa5bc](https://github.com/tomag-9/zdravy-projekt/commit/11fa5bce02642262d5cccf7e960108b5962df185))

## [3.2.3](https://github.com/tomag-9/zdravy-projekt/compare/v3.2.2...v3.2.3) (2026-09-10)


### Bug Fixes

* bump manifest to 3.2.2 (tag vytvorený manuálne, hotfix commit type release-please nerozpoznal) ([ff2149c](https://github.com/tomag-9/zdravy-projekt/commit/ff2149c8672913d9b953aaaf344b1a0266aaaa20))
* bump manifest to 3.2.2 (tag vytvorený manuálne) ([#623](https://github.com/tomag-9/zdravy-projekt/issues/623)) ([0412642](https://github.com/tomag-9/zdravy-projekt/commit/04126423e9bff5d8abfa0b386377977484373fd6))

## [3.2.0](https://github.com/tomag-9/zdravy-projekt/compare/v3.1.0...v3.2.0) (2026-09-10)


### Features

* samostatné trasy a tabuľky pre raňajky/obed/olovrant ([#613](https://github.com/tomag-9/zdravy-projekt/issues/613)) ([dda6fc1](https://github.com/tomag-9/zdravy-projekt/commit/dda6fc171d86a850fc02382af7f5628fae572ea0))


### Reverts

* main späť na v3.1.0 (odstrániť trasy + balenie diét z 3.2.0) ([#618](https://github.com/tomag-9/zdravy-projekt/issues/618)) ([d4bebfd](https://github.com/tomag-9/zdravy-projekt/commit/d4bebfd2bf6ef63d72d6be10a31b15aced768577))

## [3.1.0](https://github.com/tomag-9/zdravy-projekt/compare/v3.0.0...v3.1.0) (2026-09-09)


### Features

* **admin:** show menu B/C deadline and regroup Nadchádzajúce as cards ([c82f7d5](https://github.com/tomag-9/zdravy-projekt/commit/c82f7d5615386cf19af0dfe1a8ad5812d3dc148a))
* **edupage:** attention flag na Libelluse aj Stromčeku pre 'sA', s odklikaním ([a9e0869](https://github.com/tomag-9/zdravy-projekt/commit/a9e086919f7ddb737ee131962698f8f89733bca6))


### Bug Fixes

* **edupage:** Libellus sA zapíš ako diétu namiesto presmerovania na Stromček ([3f20d8e](https://github.com/tomag-9/zdravy-projekt/commit/3f20d8e19cc9aa1d1b78ad10e92a2db8640386c2))
* **edupage:** olovrant/diet false-flags — ZŠ Fan config fix + dismiss rozšírený na všetky flagy ([aefea3d](https://github.com/tomag-9/zdravy-projekt/commit/aefea3d3b1cdfbfe372714ff44aaf09cf3d06ef1))
* **edupage:** potvrdené uncertain diéty — Dobrodružstvo nPAR, Zdravé Brúško zšlaNM B ([e7916ef](https://github.com/tomag-9/zdravy-projekt/commit/e7916efeac463c71ed4ea8344420fbb1d48a97b4))

## [3.0.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.12.0...v3.0.0) (2026-09-08)


### ⚠ BREAKING CHANGES

* diet-component merge — zlučovanie diétnych zložiek so štandardným menu ([#568](https://github.com/tomag-9/zdravy-projekt/issues/568)) (#610)

### Features

* add scheduled maintenance mode ([51f2e93](https://github.com/tomag-9/zdravy-projekt/commit/51f2e933cfe73f36dda8e85da83acb6e91ca983a))
* **admin:** auto-collapse diet-component-merge sekcie bez výnimiek ([6fee8e5](https://github.com/tomag-9/zdravy-projekt/commit/6fee8e54b91bc347f261fe3cc13b1319cdcd982b))
* diet-component merge — zlučovanie diétnych zložiek so štandardným menu ([#568](https://github.com/tomag-9/zdravy-projekt/issues/568)) ([#610](https://github.com/tomag-9/zdravy-projekt/issues/610)) ([2533037](https://github.com/tomag-9/zdravy-projekt/commit/2533037a33081d1bab745d52abb7970c668b80d0))
* **gramage:** kaskáda zlúčenia pre kombinované diéty + presné farby diét ([#568](https://github.com/tomag-9/zdravy-projekt/issues/568)) ([a51b7c8](https://github.com/tomag-9/zdravy-projekt/commit/a51b7c8c6ab01f93ae948fe4a6b0eaa72d88780a))
* manage scheduled maintenance ([4075ae0](https://github.com/tomag-9/zdravy-projekt/commit/4075ae06ccad93daf1ca8f4a4e61d4d7b70a59a5))


### Bug Fixes

* **edupage:** desiata (British snack) prežije meal-type filter pri scrape ([19b4807](https://github.com/tomag-9/zdravy-projekt/commit/19b48070628c7f8545d3b9c83f8fa58d6fa2184a))
* **edupage:** sčítaj presmerovaný sA scrape s appkovými objednávkami Stromčeka ([3b09d72](https://github.com/tomag-9/zdravy-projekt/commit/3b09d72f51816588429275d6accfdf3101d0d52b))
* **test:** update Deutsche Schule diet expectation ([127cbd7](https://github.com/tomag-9/zdravy-projekt/commit/127cbd7b1ed2266b8408ed2976ced230a0d69f26))

## [2.12.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.11.1...v2.12.0) (2026-09-07)


### Features

* **delivery:** add cluster D ([a7898a3](https://github.com/tomag-9/zdravy-projekt/commit/a7898a32ee150300119b181cdb28c1eba03781d5))
* **objednavanie:** vypínanie jedál per deň v týždni + auto-order rešpektuje deň ([#606](https://github.com/tomag-9/zdravy-projekt/issues/606)) ([0718763](https://github.com/tomag-9/zdravy-projekt/commit/07187635e1804757c73ff05440c6186b356284e6))


### Bug Fixes

* **admin:** rozliš počty odznakov podľa menu ([255f82b](https://github.com/tomag-9/zdravy-projekt/commit/255f82b2fc8bd41b36dad9b2b8e3a11cd3433153))
* **admin:** stabilizuj British sumár a menu riadky ([4c0403f](https://github.com/tomag-9/zdravy-projekt/commit/4c0403f09fe7ff42b9c4ea396f1214f4956cea24))
* **admin:** zarovnaj príznaky prevádzky ([d9f88e3](https://github.com/tomag-9/zdravy-projekt/commit/d9f88e3c9eee6cbdedb32be348d8e80a71eb6a2c))
* **edupage:** include British diets in summary ([524389a](https://github.com/tomag-9/zdravy-projekt/commit/524389a5d30acedac1731cc174464361d83cb4e4))
* **edupage:** route Libellus Stromcek meals ([1cae8e5](https://github.com/tomag-9/zdravy-projekt/commit/1cae8e570f1176fe43493adbf691ee80a83334d1))
* **gramage:** validate component decimals ([1f02785](https://github.com/tomag-9/zdravy-projekt/commit/1f0278517093a359e951d2e51e30156198a5e9ae))
* **tests:** update tests for child portion handling and menu variant separation ([140d2c9](https://github.com/tomag-9/zdravy-projekt/commit/140d2c9cb99bdd678efe6df6878d86152ace6051))

## [2.11.1](https://github.com/tomag-9/zdravy-projekt/compare/v2.11.0...v2.11.1) (2026-09-06)


### Bug Fixes

* **docs:** refine language and remove unnecessary sections in CLAUDE.md ([7bed895](https://github.com/tomag-9/zdravy-projekt/commit/7bed8952829faf9d74896947cf408b037039e731))
* **edupage:** refine British cluster summary ([0a9744f](https://github.com/tomag-9/zdravy-projekt/commit/0a9744f3939a35ba4bec60d41d1a9f04d277c1d1))

## [2.11.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.10.0...v2.11.0) (2026-09-06)


### Features

* **admin:** zobraz príznaky balenia a olovrantu ([5cf873f](https://github.com/tomag-9/zdravy-projekt/commit/5cf873f92e64594a33388a6834108d714c530e7e))


### Bug Fixes

* **edupage:** vráť SŠV dospelých do bežného správania ([c002c59](https://github.com/tomag-9/zdravy-projekt/commit/c002c59da14b433c63ae76ad2658697243e2291b))

## [2.10.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.9.0...v2.10.0) (2026-09-06)


### Features

* **diety:** otvor výber farieb v modale ([2806f9f](https://github.com/tomag-9/zdravy-projekt/commit/2806f9f7736ef127567561d8ec49d79f2ba6bae0))


### Bug Fixes

* **diety:** odstráň samostatný "Farba" picker, len text/pozadie ([#536](https://github.com/tomag-9/zdravy-projekt/issues/536)) ([81c3986](https://github.com/tomag-9/zdravy-projekt/commit/81c39869c81685d9ba1710f1b4c339fb2e295743))

## [2.9.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.8.0...v2.9.0) (2026-09-06)


### Features

* **british:** Cluster C sumár - Menu D/VEGE1, desiata, kusový výstup ([7857367](https://github.com/tomag-9/zdravy-projekt/commit/7857367cf8f413594e681cdea2fae1882b28ea30))
* **diety:** explicitná farba textu a pozadia diéty v gramážnej tabuľke/PDF ([08bd20a](https://github.com/tomag-9/zdravy-projekt/commit/08bd20a3683f89173710b126438643ab08438169))


### Bug Fixes

* **edupage:** SŠV dospelý vždy zabaliť zvlášť, aj keď zdieľa porciu so žiakmi ([7ea490f](https://github.com/tomag-9/zdravy-projekt/commit/7ea490ffa2afdc860336467123e784c44af0ef23))

## [2.8.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.7.0...v2.8.0) (2026-09-04)


### Features

* **admin:** diéty bez ručného poradia, zoskupené podľa počtu zložiek ([c3c9f9b](https://github.com/tomag-9/zdravy-projekt/commit/c3c9f9b2a275fe8c6eaaf11e53bc2a93df8f31aa))
* **admin:** prerob detail prevádzky na Údaje/Objednávanie/Diéty + poznámka k diéte ([fbe2fdc](https://github.com/tomag-9/zdravy-projekt/commit/fbe2fdced218510d0dec1f9777dee34242ac9206))
* **admin:** zobraz poznámku k diéte v gramážnej tabuľke a PDF ([245e1dd](https://github.com/tomag-9/zdravy-projekt/commit/245e1dd70c0ca1d6725603f6ee32e9eb16e36b6c))


### Bug Fixes

* **admin:** dropni osirelú starú visible_diets tabuľku, blokovala mazanie prevádzky ([625c567](https://github.com/tomag-9/zdravy-projekt/commit/625c5677341d218aafcc875d37e89dc3b88e7750))
* **admin:** sprav 0096 (drop starej visible_diets tabuľky) plne reverzibilnú ([67f5b4b](https://github.com/tomag-9/zdravy-projekt/commit/67f5b4bc5689dde86e8c7044519246501b560df3))
* **edupage:** hodinový preview scrape berie N pracovných dní, nie kalendárnych ([e74f47d](https://github.com/tomag-9/zdravy-projekt/commit/e74f47df38e7c3f2decb2afb73fe59875766ee3e))

## [2.7.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.6.0...v2.7.0) (2026-09-04)


### Features

* **admin:** kusovo/MŠ počet a rozpis Menu A/B/C v klastrovom súhrne ([37c18f6](https://github.com/tomag-9/zdravy-projekt/commit/37c18f67ea1dbeb800bfe2b4ff9c800f721503e0))
* **admin:** vráť rozpis po jedlách bez R/Ob/Ol skratky (bez rohových odznakov) ([77383ce](https://github.com/tomag-9/zdravy-projekt/commit/77383ce1a8ba66e04d714e6ae43c9b3e3b8ec759))
* **edupage:** nastavenie „dospelí zvlášť" na prevádzke ([2dc2ea4](https://github.com/tomag-9/zdravy-projekt/commit/2dc2ea460f6b34de942f5740b6904c750538e114))
* **edupage:** scrape log ukazuje jedlá per deň (meals_by_date) ([a4cd8b3](https://github.com/tomag-9/zdravy-projekt/commit/a4cd8b3c8a81aeb65e346f44898fe248766cefe2))


### Bug Fixes

* **docs:** clarify production access rules in CLAUDE.md ([ba14697](https://github.com/tomag-9/zdravy-projekt/commit/ba1469738cbfa9c2b20e6427924d7df12dc4f460))
* **gramage:** "zvlast" riadok stráca počet v composite formáte (0 + 0) ([baac4cc](https://github.com/tomag-9/zdravy-projekt/commit/baac4cca14b7b01d633723b5498c8c9e04d08d89))
* **gramage:** Dospelý (SŠ) na vlastnom riadku pre každé menu ([6ebbc93](https://github.com/tomag-9/zdravy-projekt/commit/6ebbc93f557c3322ddf25f02721b3aabacdba11c))
* **order:** Celodenná objednávka prežije aj bez localStorage draftu ([f09a021](https://github.com/tomag-9/zdravy-projekt/commit/f09a021d31db2e6e2e7681fdc9b07da948ec05ca))
* **order:** submit nesmie prepísať nedotknuté jedlo starým draftom ([fc779c1](https://github.com/tomag-9/zdravy-projekt/commit/fc779c15820c246a81ab0866e8559d6271d3507d))

## [2.6.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.5.0...v2.6.0) (2026-09-04)


### Features

* **admin:** počet porcií v rohu každej bunky gramáže + rozpis po jedlách bez R/Ob/Ol ([6efc4de](https://github.com/tomag-9/zdravy-projekt/commit/6efc4de7553747c2d7a3c8cbe615316de00186d5))


### Bug Fixes

* **edupage:** 'NoBanán' payer prefix sa strácal, 'NO MILK' prebilo zvyšok kombinácie ([793db69](https://github.com/tomag-9/zdravy-projekt/commit/793db69f51064a132339e738cd9700c136fd7f88))
* **edupage:** ZŠ Malokarpatská "očakávaný olovrant chýba" bola falošná ([79a1095](https://github.com/tomag-9/zdravy-projekt/commit/79a1095ba384fb634621f0e2a8f9c56fd5c71870))

## [2.5.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.4.0...v2.5.0) (2026-09-03)


### Features

* **admin:** počet porcií do prvej bunky každej skupiny v CELKOM riadku gramáže ([2145e6a](https://github.com/tomag-9/zdravy-projekt/commit/2145e6a02c2d7d71b02c197134df8b4fa70efa46))
* **admin:** zjednotiť dátumový prepínač na Kontrole objednávok s Gramážou ([b483dd1](https://github.com/tomag-9/zdravy-projekt/commit/b483dd17fe397bd06b18bd5972f1e7dcce6c7e13))
* **auto-order:** Bystrá škôlky - raňajky z predošlého obeda ([46f36fe](https://github.com/tomag-9/zdravy-projekt/commit/46f36fea0196100b36768af25a0929c44a8b6f9a))


### Bug Fixes

* **client:** URL dátum sa do objednávkového formulára uplatňoval s oneskorením ([806bd8c](https://github.com/tomag-9/zdravy-projekt/commit/806bd8c3a9b7a79d4de40319824001cbe7c86b7c))
* **edupage:** Krásňanko/Školička/Naša škola poznania skratky + Benjamíny multi-prevádzka súhrn ([dd38037](https://github.com/tomag-9/zdravy-projekt/commit/dd38037e3d54f83a17d09be8a6438683def5d34b))
* **gramage:** počet Menu B/C variantov sa v zlúčenom riadku prepisoval, nie sčítaval ([634dd17](https://github.com/tomag-9/zdravy-projekt/commit/634dd17816add863c11bb9cace0cbce06d195adc))

## [2.4.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.3.0...v2.4.0) (2026-09-03)


### Features

* **admin:** kompaktná hlavička gramážnej tabuľky v jednom riadku ([cf67fdf](https://github.com/tomag-9/zdravy-projekt/commit/cf67fdf961e91e57e71f22e6f9d518f0033710df))
* **admin:** zapamätanie Nastavení tabuľky, ukotvenie tlačidiel vpravo, search len scrolluje ([42a1719](https://github.com/tomag-9/zdravy-projekt/commit/42a1719484453cfa985058085792450cddd3e288))


### Bug Fixes

* **admin:** 'Zobraziť všetko rozbalené' reálne rozbaľuje, prepis na 'prevádzky' ([174ca8d](https://github.com/tomag-9/zdravy-projekt/commit/174ca8d3b994d1a409cecc98a9477f995396b30e))
* **edupage:** opravené porcia kódy pre Fantastickú Školu a Dobrodružstvo ([8ed2a50](https://github.com/tomag-9/zdravy-projekt/commit/8ed2a5014eb208ff292c06cffdf0e626355a4514))
* **edupage:** SŠ Veterinárna Vege je samostatné menu, nie diéta na Klasiku ([1c51778](https://github.com/tomag-9/zdravy-projekt/commit/1c51778ec29799c00b7d9bccfeedd697d1178239))

## [2.3.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.2.0...v2.3.0) (2026-09-03)


### Features

* **admin:** vyhľadávanie a editácia poznámky v gramážnej tabuľke, jasnejšia B/C deadline hláška ([6543e94](https://github.com/tomag-9/zdravy-projekt/commit/6543e94d2a0697127ccc31d51639cf3ed0443f28))


### Bug Fixes

* **admin:** gramážna tabuľka padala na desatinnej čiarke v unit_exception ([f0a9d68](https://github.com/tomag-9/zdravy-projekt/commit/f0a9d683f633f75fe7b2184cef5e9ca3c22fce56))
* **admin:** Nastavenia tabuľky modál sa neblikal pri zmene filtra ([1c27413](https://github.com/tomag-9/zdravy-projekt/commit/1c27413fb47e5fc6615117937eb8d8f287dc0509))
* **ci:** quote the if: expression in production.yml (invalid YAML) ([568143b](https://github.com/tomag-9/zdravy-projekt/commit/568143bc01ea119c8d61b1925a4072de87329831))
* **ci:** release-please auto-merge + skip deploy on version-bump ([#571](https://github.com/tomag-9/zdravy-projekt/issues/571)) ([6f645e0](https://github.com/tomag-9/zdravy-projekt/commit/6f645e0b427ecab5d99f812ebfd6e423d00b939d))
* **ci:** skip production deploy for release-please version-bump commits ([8925569](https://github.com/tomag-9/zdravy-projekt/commit/89255695a6f3ee3f8a1dfeeb532f34df750c9eda))
* **client:** deň so zdieľanou objednávkou vo viac prevádzkach nemá ukazovať "žiadna objednávka" ([b7f2b61](https://github.com/tomag-9/zdravy-projekt/commit/b7f2b61b567b5dcacf796a04d22c84f49e320709))
* **client:** kopírovanie medzi chodmi obchádzalo strop Menu B/C/D po termíne ([78fdca3](https://github.com/tomag-9/zdravy-projekt/commit/78fdca361fe03cb18afc86bfaa445f924882e0b4))
* **edupage:** hodinový preview scrape neprepisuje jedlo po jeho deadline scrape ([bd205f4](https://github.com/tomag-9/zdravy-projekt/commit/bd205f4817c1047e604bd246d0ed62cc068fe52f))
* **edupage:** Libellus a Stromček zdieľajú feed — sA nemá počítať do Libellusovho Klasiku ([314e55f](https://github.com/tomag-9/zdravy-projekt/commit/314e55f2c1cbef5f942d3225b31abf0c8fe05be7))
* **edupage:** NMNE/nMnEgg skratka strácala NO EGG časť diéty ([#574](https://github.com/tomag-9/zdravy-projekt/issues/574)) ([6b6944e](https://github.com/tomag-9/zdravy-projekt/commit/6b6944e6034fa5d7f4f5c746c01e8acb1c88a7d3))
* **gramage:** diétny súhrn nesmie počítať dieťa 3x cez raňajky/obed/olovrant ([2e318b3](https://github.com/tomag-9/zdravy-projekt/commit/2e318b3793d84f5707930f963591b0b5be430b7d))
* **gramage:** diétny súhrn nesmie počítať dieťa 3x cez raňajky/obed/olovrant ([#572](https://github.com/tomag-9/zdravy-projekt/issues/572)) ([48c602e](https://github.com/tomag-9/zdravy-projekt/commit/48c602eb5929b8b66cf2e21c37ba26a68ee6b535))
* **gramage:** diétny súhrn nesmie počítať dieťa 3x cez raňajky/obed/olovrant ([#573](https://github.com/tomag-9/zdravy-projekt/issues/573)) ([364b059](https://github.com/tomag-9/zdravy-projekt/commit/364b0598bbed9b138f197e389405094b52c9d5e0))

## [2.2.0](https://github.com/tomag-9/zdravy-projekt/compare/v2.1.0...v2.2.0) (2026-09-02)


### Features

* „Zabaliť zvlášť" — označenie porcií na samostatné zabalenie ([6fdc70c](https://github.com/tomag-9/zdravy-projekt/commit/6fdc70c3eebb6ed4775f413d0f1aae04d59b46fb))
* add delivery layout overview ([#374](https://github.com/tomag-9/zdravy-projekt/issues/374)) ([234ede3](https://github.com/tomag-9/zdravy-projekt/commit/234ede3da5e9c3e495d80fe2aebae4991c663c93))
* add delivery layout overview ([#374](https://github.com/tomag-9/zdravy-projekt/issues/374)) ([3960030](https://github.com/tomag-9/zdravy-projekt/commit/3960030c7ad6c07cff65b937003b84b2aed762e0))
* Add Edupage scraping functionality ([#308](https://github.com/tomag-9/zdravy-projekt/issues/308)) ([cede19d](https://github.com/tomag-9/zdravy-projekt/commit/cede19de46927ac411363af61389d3d6484677d6))
* add holiday management functionality ([#186](https://github.com/tomag-9/zdravy-projekt/issues/186)) ([88e6cfa](https://github.com/tomag-9/zdravy-projekt/commit/88e6cfa89c5417098f3b86967ba465f7e1f25d78))
* add mobile-only PWA install prompt and enhance notification handling ([1ce13df](https://github.com/tomag-9/zdravy-projekt/commit/1ce13df9800e2cd9f9eccb9259a2b9c74be2ac7a))
* add observability dashboard, login metric, and Alloy container filter ([89f2eb8](https://github.com/tomag-9/zdravy-projekt/commit/89f2eb88138aa608818f9fbe7eb58f1ff819f3ed))
* add onboarding tour with context ([#185](https://github.com/tomag-9/zdravy-projekt/issues/185)) ([cc2e999](https://github.com/tomag-9/zdravy-projekt/commit/cc2e999fd309021f7d0d71b7147aaca24d243ebf))
* add repo-managed backend CPU alert ([b8f5ace](https://github.com/tomag-9/zdravy-projekt/commit/b8f5ace4bbde73e746abb2956ca7e56b138879ab))
* add repo-managed backend CPU alert ([a37364f](https://github.com/tomag-9/zdravy-projekt/commit/a37364f7d738b38b422cc2e12b788f450b416f33))
* add user registration ([#80](https://github.com/tomag-9/zdravy-projekt/issues/80)) ([fc44b84](https://github.com/tomag-9/zdravy-projekt/commit/fc44b842cf93d20ecde156b0c16fdf9076e35876))
* add vapid keys ([#181](https://github.com/tomag-9/zdravy-projekt/issues/181)) ([20234a3](https://github.com/tomag-9/zdravy-projekt/commit/20234a30b7b35f0445e6a05d4fa1c34606cf42ba))
* Add website UI kit components including Header, Hero, DietPicker, Founders, Partners, and Footer ([cf87e99](https://github.com/tomag-9/zdravy-projekt/commit/cf87e99050b78342c28b31bdb72540eaccd71b65))
* admin dash ([#182](https://github.com/tomag-9/zdravy-projekt/issues/182)) ([9f069cd](https://github.com/tomag-9/zdravy-projekt/commit/9f069cd2ea6e1b58fce4ce0e754afcff52dc7f6c))
* admin dash ([#69](https://github.com/tomag-9/zdravy-projekt/issues/69)) ([f8f1753](https://github.com/tomag-9/zdravy-projekt/commit/f8f1753ed28c721fa9313827661d411dca481ef2))
* admin dashboard ([#304](https://github.com/tomag-9/zdravy-projekt/issues/304)) ([93b03ef](https://github.com/tomag-9/zdravy-projekt/commit/93b03efc4ea45701886c669e589271b99667f65e))
* admin dashboard v2 ([#307](https://github.com/tomag-9/zdravy-projekt/issues/307)) ([993386b](https://github.com/tomag-9/zdravy-projekt/commit/993386b4e182c8fb01ed9a83aef376d495f8d972))
* admin jedlanicek ([#135](https://github.com/tomag-9/zdravy-projekt/issues/135)) ([113a8a4](https://github.com/tomag-9/zdravy-projekt/commit/113a8a41ae6d070878ae395cb0130a27e1e18384))
* admin objednávka = klientsky formulár, raňajky/olovrant len menu A ([afba747](https://github.com/tomag-9/zdravy-projekt/commit/afba7473b0bfa49a2e6fb356f5b15cb7941956f6))
* admin panel ([#20](https://github.com/tomag-9/zdravy-projekt/issues/20)) ([175b0c6](https://github.com/tomag-9/zdravy-projekt/commit/175b0c6dfd1541e404c5a66f6e4dcbe899aacb48))
* **admin:** allow deleting a celok with FK-protection error handling ([1451f7f](https://github.com/tomag-9/zdravy-projekt/commit/1451f7f93498f2f3bf42086065efd0e5aa8ab008))
* **admin:** automaticky vygeneruj a cachuj PDF gramáže pri uzavretí dňa ([#528](https://github.com/tomag-9/zdravy-projekt/issues/528)) ([b048521](https://github.com/tomag-9/zdravy-projekt/commit/b048521537f913fc1a9e9689ce6c324c4d46e4d0))
* **admin:** celok CRUD (create + cascade delete) and auth hardening ([#460](https://github.com/tomag-9/zdravy-projekt/issues/460)-[#463](https://github.com/tomag-9/zdravy-projekt/issues/463)) ([9672d2d](https://github.com/tomag-9/zdravy-projekt/commit/9672d2d5552a4ffd14cc734bac9656ff684b9271))
* **admin:** čitateľná tabuľka udalostí — mená, dvojriadkový čas, farby podľa úkonu ([5919ef2](https://github.com/tomag-9/zdravy-projekt/commit/5919ef2c89661a234351fed2b1ec5707ebc50730))
* **admin:** čitateľná tabuľka udalostí — mená, dvojriadkový čas, farby podľa úkonu ([775f3d0](https://github.com/tomag-9/zdravy-projekt/commit/775f3d0d5a39874611379d02c0a815579af34065))
* **admin:** close a day globally and export the closed order table ([#417](https://github.com/tomag-9/zdravy-projekt/issues/417)) ([fa3920e](https://github.com/tomag-9/zdravy-projekt/commit/fa3920e2e4f32b69a9463bded7aa04833a70636d))
* **admin:** dodanie podkladov skips weekends, drops PDF/XLSX generation ([d8cd384](https://github.com/tomag-9/zdravy-projekt/commit/d8cd384dbe880d96230170e995336f797b9c6644))
* **admin:** klikateľné názvy prevádzok v tabuľke a dodaní podkladov ([#527](https://github.com/tomag-9/zdravy-projekt/issues/527)) ([b3dd8c9](https://github.com/tomag-9/zdravy-projekt/commit/b3dd8c9cf7ac99a1324853108f7bdc076a3faf81))
* **admin:** manuálny scrape British School, detailný log a Nadchádzajúce crony ([0ddebdf](https://github.com/tomag-9/zdravy-projekt/commit/0ddebdf292c76264a226fdb4b604693c7525443f))
* **admin:** použiteľná admin konzola na mobile ([#480](https://github.com/tomag-9/zdravy-projekt/issues/480)) ([d4efd20](https://github.com/tomag-9/zdravy-projekt/commit/d4efd20d9bd1e71123133aad419172a700da376f))
* **admin:** použiteľná admin konzola na mobile ([#480](https://github.com/tomag-9/zdravy-projekt/issues/480)) ([f80e23b](https://github.com/tomag-9/zdravy-projekt/commit/f80e23b0753d8a6fcb127f38265cb5a757b901e9))
* **admin:** restrict per-prevádzka which portion sizes can be ordered ([#416](https://github.com/tomag-9/zdravy-projekt/issues/416)) ([7e2fd34](https://github.com/tomag-9/zdravy-projekt/commit/7e2fd34d67cd33e697ac495270539099fc14f51c))
* **admin:** rozpis diét v prehľade prevádzok (klasik + počet za každú diétu) ([9cf3aea](https://github.com/tomag-9/zdravy-projekt/commit/9cf3aeaef9a6ce4a5a51ab91e1ab666732d58abc))
* **admin:** rozpíš konkrétne diéty v histórii objednávok ([1927b02](https://github.com/tomag-9/zdravy-projekt/commit/1927b02b18887b7b5447e3304d45ccbd49d38c7c))
* **admin:** rozpíš počty aj podľa menu písmena v detaile prevádzky ([b6afd0d](https://github.com/tomag-9/zdravy-projekt/commit/b6afd0d71b39931796ba49f16dc850b074ab4da9))
* **admin:** split prevádzka CRUD between /facilities and /facilities/:id ([8708c03](https://github.com/tomag-9/zdravy-projekt/commit/8708c03a141a1459b143bbe0194f79b2a676f172))
* **admin:** swatch picker for diet color instead of raw color input ([a91ba8b](https://github.com/tomag-9/zdravy-projekt/commit/a91ba8bf15c664652fa460d0fc23d96f0ddc884d))
* **admin:** sync celok CRUD + cascade delete + auth hardening from main ([#460](https://github.com/tomag-9/zdravy-projekt/issues/460)-[#464](https://github.com/tomag-9/zdravy-projekt/issues/464)) ([5ce6a6c](https://github.com/tomag-9/zdravy-projekt/commit/5ce6a6c006562b62c1b355ffd80488e9bacf7b82))
* **admin:** unlock a closed day for editing again ([#419](https://github.com/tomag-9/zdravy-projekt/issues/419)) ([db22d3f](https://github.com/tomag-9/zdravy-projekt/commit/db22d3f4252d8e94f6d4b82050a8f071ff70d5a1))
* **admin:** zvýrazniť dnes/zajtra/pozajtra pri dátume novej objednávky ([7ee6393](https://github.com/tomag-9/zdravy-projekt/commit/7ee6393bf9c60b921a557df8e5d6bf7503cfdf5f))
* **audit:** add EventLog audit trail for admin actions ([7105b15](https://github.com/tomag-9/zdravy-projekt/commit/7105b15c86222634961bf57d981279bb1259aad2))
* **audit:** loguj zmeny systémových nastavení vrátane uzávierok ([085cd42](https://github.com/tomag-9/zdravy-projekt/commit/085cd42ce412c9723eedb1bb31095eb279fc82c7))
* **audit:** zapisuj aj ostatné administrátorské zmeny, nielen celky a prevádzky ([61ec8a2](https://github.com/tomag-9/zdravy-projekt/commit/61ec8a297e3e962ad1ce67b7d33b266917cf007f))
* **audit:** zapisuj aj ostatné administrátorské zmeny, nielen celky a prevádzky ([b06cccb](https://github.com/tomag-9/zdravy-projekt/commit/b06cccbe73e27f5ca3654f03377032276f73496f))
* **audit:** zapisuj každý cron beh, nielen ten preskočený ([c181f66](https://github.com/tomag-9/zdravy-projekt/commit/c181f6648bdffd5c073f84cc5f93826033ca29f9))
* **audit:** zapisuj každý cron beh, nielen ten preskočený ([a5507b3](https://github.com/tomag-9/zdravy-projekt/commit/a5507b3d64a0e94373848b80c24e9e9f14434ce8))
* **auth:** import operation logins by facility group ([b296b43](https://github.com/tomag-9/zdravy-projekt/commit/b296b4312c4a3b505f349c6ebc9c79b1d0f6e894))
* auto-order ([#23](https://github.com/tomag-9/zdravy-projekt/issues/23)) ([cf47b3e](https://github.com/tomag-9/zdravy-projekt/commit/cf47b3e4158c88e7c5881abea6aad6f2300674f7))
* **backend:** enable database connection pooling ([#35](https://github.com/tomag-9/zdravy-projekt/issues/35)) ([2188dd3](https://github.com/tomag-9/zdravy-projekt/commit/2188dd3a24761e6c2ea9b7676eb06f6ca13e6ec1))
* **backend:** skip cron tasks on weekends and configured holidays ([b8e9aba](https://github.com/tomag-9/zdravy-projekt/commit/b8e9aba71e90a14f8c88e46585f67591978cc585))
* British School vlastný scrape 12:15 + farby/čiary v tabuľke gramáže ([#537](https://github.com/tomag-9/zdravy-projekt/issues/537)) ([adf1fb4](https://github.com/tomag-9/zdravy-projekt/commit/adf1fb490b5d10ae6f372c1d6067e0ed9042a238))
* celodenná objednávka,inbox správy, špeciálna diéta ([#295](https://github.com/tomag-9/zdravy-projekt/issues/295)) ([7244a0b](https://github.com/tomag-9/zdravy-projekt/commit/7244a0b722ec6ed2a09a3ef1b2f197e34cda929b))
* celok→prevádzka objednávky per prevádzka ([#375](https://github.com/tomag-9/zdravy-projekt/issues/375)) ([e6c52b9](https://github.com/tomag-9/zdravy-projekt/commit/e6c52b9e89c13cc7fe6b64b54b8473530fa9414e))
* celok→prevádzka objednávky per prevádzka ([#375](https://github.com/tomag-9/zdravy-projekt/issues/375)) ([08e67cf](https://github.com/tomag-9/zdravy-projekt/commit/08e67cf34c294268454f0128ee5957dd6cda3dd1))
* client detail ([#157](https://github.com/tomag-9/zdravy-projekt/issues/157)) ([99b307b](https://github.com/tomag-9/zdravy-projekt/commit/99b307b81579aa512c270a4043763e1f1931eb31))
* **client:** de-emphasize the "Zabaliť zvlášť" box styling ([d6dc088](https://github.com/tomag-9/zdravy-projekt/commit/d6dc088ae205208ef0631807cf3499e789983145))
* **client:** merge menu+diet duplicate row in pack-separately list ([#415](https://github.com/tomag-9/zdravy-projekt/issues/415)) ([791a54d](https://github.com/tomag-9/zdravy-projekt/commit/791a54de22cc4921e9bce6f31d0d4430586aa640))
* **cluster:** premenuj Výdaj → Cluster ([#531](https://github.com/tomag-9/zdravy-projekt/issues/531)) ([4022b42](https://github.com/tomag-9/zdravy-projekt/commit/4022b4292f973f3821b5c47aa21fd321db1c32d9))
* **compare-real:** porovnávaj proti produkcii, nie proti lokálnej DB ([4499783](https://github.com/tomag-9/zdravy-projekt/commit/4499783ff864e71f90a103557708aca94a70be51))
* **compare-real:** porovnávaj proti produkcii, nie proti lokálnej DB ([d5e2548](https://github.com/tomag-9/zdravy-projekt/commit/d5e25482ae4fb7b6158b6fd1f4b8d0a409d417b5))
* daily report ([#24](https://github.com/tomag-9/zdravy-projekt/issues/24)) ([6246b66](https://github.com/tomag-9/zdravy-projekt/commit/6246b661b4579882aaf488941ddc97611df43504))
* **db:** add EduPage connection model ([2599eab](https://github.com/tomag-9/zdravy-projekt/commit/2599eab094565dc22e94a16721cdd821fc2ebd69))
* **db:** add model consistency audit ([dd30509](https://github.com/tomag-9/zdravy-projekt/commit/dd30509b30238cc48b6af49539ddc191ed1b7906))
* **deploy:** log a new-version EventLog entry on successful deploy ([c67bc1e](https://github.com/tomag-9/zdravy-projekt/commit/c67bc1e2081793730c5200bdb7208afe17cf6724))
* **dev:** prihlásenie jedným klikom za každú rolu ([dd0174a](https://github.com/tomag-9/zdravy-projekt/commit/dd0174ae8b24ba09d421653eb50cc8cc6a5eb855))
* **diet:** expose diet-to-menu-variant link, read-only ([#420](https://github.com/tomag-9/zdravy-projekt/issues/420)) ([e2a4ec4](https://github.com/tomag-9/zdravy-projekt/commit/e2a4ec40ef3912acad22fe8267b2cc985a74a804))
* Docker Swarm production deployment with nginx hardening ([65d34cc](https://github.com/tomag-9/zdravy-projekt/commit/65d34cc58eeead4f77270a412609438ef471041c))
* **docs:** add user manual for operations ([6ca2820](https://github.com/tomag-9/zdravy-projekt/commit/6ca2820e23194b4896b52cb1a680f409e7a4d593))
* dump dependencies and enhance audit logging ([#412](https://github.com/tomag-9/zdravy-projekt/issues/412)) ([a4f8bc0](https://github.com/tomag-9/zdravy-projekt/commit/a4f8bc0a3e4e3e5b842968a176479bcf996d6b87))
* edupage jedalnicek import ([#306](https://github.com/tomag-9/zdravy-projekt/issues/306)) ([c239ba3](https://github.com/tomag-9/zdravy-projekt/commit/c239ba3e1ef9c57fa35467cea1e0998c8189eb1c))
* Edupage uploads and Jedálniček import ([#296](https://github.com/tomag-9/zdravy-projekt/issues/296)) ([c44b944](https://github.com/tomag-9/zdravy-projekt/commit/c44b9445be925d1692c5bd4c906358cc893e22b2))
* **edupage:** hodinový priebežný scrape na dnes+2, manuálny scrape per prevádzka, dashboardy odomknuté na dnes+2 ([5115bc0](https://github.com/tomag-9/zdravy-projekt/commit/5115bc0e5ee856747082558db1a0e6564941621f))
* **edupage:** neznáma diéta už nezhltne porcie a whitelist ide z DB ([79f12a5](https://github.com/tomag-9/zdravy-projekt/commit/79f12a5ebd7143d127f3e40ade2430458478ea61))
* **edupage:** onboard Cvernička, Montessori, Dobrodružstvo ZŠ split; rename SZŠ FAN/MŠ Prameň ([3607551](https://github.com/tomag-9/zdravy-projekt/commit/360755127cd835ba00329f2158aeb187c50d4e45))
* **edupage:** onboarduj British School na EduPage ([#531](https://github.com/tomag-9/zdravy-projekt/issues/531)) ([47f5f0a](https://github.com/tomag-9/zdravy-projekt/commit/47f5f0a2432e8bb8ebaa0fc61e178a89f726b119))
* **edupage:** potvrdené diétne mapovania + auto-preklopenie Dodania podkladov o 21:00 ([4b439ec](https://github.com/tomag-9/zdravy-projekt/commit/4b439ec8a5231521228ee80141482555e720e0d1))
* **edupage:** predbežný Menu B/C scrape 1-2 dni vopred (napojené na obedový beh) ([fb118d2](https://github.com/tomag-9/zdravy-projekt/commit/fb118d2d80c8f927787c744a6c16d0e9926d7684))
* **edupage:** prepoj CMŠ Pezinok na EduPage ([d06d264](https://github.com/tomag-9/zdravy-projekt/commit/d06d26496be2fb212edd8cebb0ca207ba7cc000c))
* **edupage:** pridaj config pre Cverničku, olovrant EduPage &lt; realita ([31ffbce](https://github.com/tomag-9/zdravy-projekt/commit/31ffbcea5a01cac7b83a8f08fb7a59c77db70ab7))
* **edupage:** raňajky = obed pre celodennú dochádzku (Pramienok, Montessori Borínska MŠ) ([8a82455](https://github.com/tomag-9/zdravy-projekt/commit/8a824558c138ae0017a0695be8768a02864b40b9))
* **edupage:** rozpojenie uzávierky a scrapu, defaultné časy, čitateľné Nadchádzajúce ([#553](https://github.com/tomag-9/zdravy-projekt/issues/553)) ([7e5ad12](https://github.com/tomag-9/zdravy-projekt/commit/7e5ad12f17cfac7dbe11bbc498c929d61b4d2fd8))
* **edupage:** Školička – nové ŠPECI dieťa v triede Lúka ([60f753c](https://github.com/tomag-9/zdravy-projekt/commit/60f753c51bb719ab13fa9f68a2380dbfb5c54a5a))
* **edupage:** Školička – nové ŠPECI dieťa v triede Lúka ([78a1ac9](https://github.com/tomag-9/zdravy-projekt/commit/78a1ac93b94c014a3930b9063361966c32366271))
* **email:** aktualizuj text uvítacieho e-mailu (klient, 26.8.2026) ([ca62404](https://github.com/tomag-9/zdravy-projekt/commit/ca624046907edc3dedb5f2353612fc592ca0adaf))
* **email:** aktualizuj text uvítacieho e-mailu (klient, 26.8.2026) ([265341c](https://github.com/tomag-9/zdravy-projekt/commit/265341c85e38dfb835b5d22f76d64ac372903bad))
* **email:** prilož návod pre prevádzky k prvému set-password mailu ([2fdf3a1](https://github.com/tomag-9/zdravy-projekt/commit/2fdf3a185a0c912f481920a1a2fc6de16206b88e))
* **email:** úvodný list klienta pred odkazom na nastavenie hesla ([87d7d1e](https://github.com/tomag-9/zdravy-projekt/commit/87d7d1e56bdb7ea7b6bac3943778c570420f443b))
* enhance desktop experience with responsive layouts and new styles ([3a5da61](https://github.com/tomag-9/zdravy-projekt/commit/3a5da6149c3593465ae43ec1d249684a85eb3aec))
* enhance login page with password visibility toggle and responsive styles ([8925a22](https://github.com/tomag-9/zdravy-projekt/commit/8925a2204b3103003887f511f85e0ac70df78f23))
* enhance user interaction styles with improved selection and tap highlight handling ([59490f3](https://github.com/tomag-9/zdravy-projekt/commit/59490f3c46e6119f7ddfb84a6df037a97a26f82d))
* enhance viewport height handling and prevent overscroll behavior ([170dfe1](https://github.com/tomag-9/zdravy-projekt/commit/170dfe1e4413b514512e7d6a21fd4e73a6bde7d2))
* finish medium review fixes ([#290](https://github.com/tomag-9/zdravy-projekt/issues/290)) ([309a73c](https://github.com/tomag-9/zdravy-projekt/commit/309a73c6dbaf61bf711279290847d6c09b35fddb))
* **frontend:** diet color palette, reorder, composite colors ([#433](https://github.com/tomag-9/zdravy-projekt/issues/433)) ([2c85f05](https://github.com/tomag-9/zdravy-projekt/commit/2c85f057669e0b57d366840b3a95f6f666c94d1e))
* **frontend:** enhance profile management + tests ([#39](https://github.com/tomag-9/zdravy-projekt/issues/39)) ([2065013](https://github.com/tomag-9/zdravy-projekt/commit/20650130bfe8feb4c041418b46121dc6b6526f53))
* **frontend:** normalize celok/prevádzka search for case/diacritics/punctuation ([95a7283](https://github.com/tomag-9/zdravy-projekt/commit/95a728371dc82042111df109d4980c164efc59ac))
* **gramage:** one spec behind the screen ([#466](https://github.com/tomag-9/zdravy-projekt/issues/466)) ([de64192](https://github.com/tomag-9/zdravy-projekt/commit/de6419240cdf73276971e6e5ae52c6dc9a6544a4))
* **gramage:** sumáre pre 3 klastre v tabuľke ([#531](https://github.com/tomag-9/zdravy-projekt/issues/531)) ([fbe6dac](https://github.com/tomag-9/zdravy-projekt/commit/fbe6dac26c63bb1346197c67af60baea4d3db29e))
* **gramaz,logy:** zruš stĺpec Poznámka, tooltip na skrátený text, deň v logu objednávok ([ae75c82](https://github.com/tomag-9/zdravy-projekt/commit/ae75c82cb062a8c35f7737f2b0b09717df50b03e))
* **gramaz:** admin toggle 'Olovrant ide s obedom' so zltym zvyraznenim ([5401a84](https://github.com/tomag-9/zdravy-projekt/commit/5401a841ea9b37c29c34d4167fa15cb099414db7))
* **gramaz:** dátumový prepínač vpravo od nadpisu, cluster vedľa filtra jedál ([878718e](https://github.com/tomag-9/zdravy-projekt/commit/878718e7326df4e274981157ba03a68c2209ce89))
* **gramaz:** diétny rozpad aj v súhrnoch (Sumár 1/2, Sumár 1 a 2, Sumár dokopy) ([2cee2c3](https://github.com/tomag-9/zdravy-projekt/commit/2cee2c3d8cee479c06f9bb6aa97ae41230ab71fa))
* **gramaz:** hlavny udaj obedov, zluc jedla do riadku, upravy PDF ([#527](https://github.com/tomag-9/zdravy-projekt/issues/527), [#528](https://github.com/tomag-9/zdravy-projekt/issues/528), [#529](https://github.com/tomag-9/zdravy-projekt/issues/529)) ([fac73c7](https://github.com/tomag-9/zdravy-projekt/commit/fac73c78bce4fe9f1d5c951347aa8c99e7442d00))
* **gramaz:** nastavenia tabuľky presunuté do modálu, nové prepínače ([d34844d](https://github.com/tomag-9/zdravy-projekt/commit/d34844d5cac4ad9940b3f4e51a2908fe89eca1a5))
* **gramaz:** pätka tabuľky ukazuje súčet prepočítaný na MŠ porcie (billing_portion_coefficients) ([81dd502](https://github.com/tomag-9/zdravy-projekt/commit/81dd502cc2f7d48a875b6e98cea0c01d622bc9a3))
* **gramaz:** posledný riadok pätky je SUM TOTAL OBED MŠ ([8f096ef](https://github.com/tomag-9/zdravy-projekt/commit/8f096eff87d5ff40203890054f7367fd72ef6431))
* **gramaz:** poznámka ku konkrétnej diéte (Diet.description) je vidno priamo v tabuľke aj PDF ([9248dc3](https://github.com/tomag-9/zdravy-projekt/commit/9248dc3ec67417e21019eb87a7eac8f254bf4415))
* **gramaz:** sumar porcii - 5 pomenovanych sekcii POCET/PREPOCET/KLASIK/DIETY/SPOLU ([#532](https://github.com/tomag-9/zdravy-projekt/issues/532)) ([677d588](https://github.com/tomag-9/zdravy-projekt/commit/677d588e677d615976754308fbe0764e4c61b44e))
* **gramaz:** sumar prerobeny - kazdy cluster S DIETAMI MS + 3 riadky, prepocet cez PortionType.coefficient ([#532](https://github.com/tomag-9/zdravy-projekt/issues/532)) ([98b7d87](https://github.com/tomag-9/zdravy-projekt/commit/98b7d87b0c6f3cf3c956432f51e28791524fcaa4))
* h1 dailyorder data validation ([#288](https://github.com/tomag-9/zdravy-projekt/issues/288)) ([0534e29](https://github.com/tomag-9/zdravy-projekt/commit/0534e292a1a623cb9ae047e9ff6f454a97b25ce8))
* **home:** história za celok s rozpisom podľa prevádzok ([0bbb1e5](https://github.com/tomag-9/zdravy-projekt/commit/0bbb1e59cc8e5e6b18c111c4a55bd53aa4cf924b))
* implement apploadingscreen ([#183](https://github.com/tomag-9/zdravy-projekt/issues/183)) ([d2eec3a](https://github.com/tomag-9/zdravy-projekt/commit/d2eec3af3a2b46eed248518963955f8349ff2103))
* implement password reset with email notifications ([#26](https://github.com/tomag-9/zdravy-projekt/issues/26)) ([13e7651](https://github.com/tomag-9/zdravy-projekt/commit/13e7651f3afbbb6c4c565020401f4c6bfb0680b4))
* implement push reminder task management ([#206](https://github.com/tomag-9/zdravy-projekt/issues/206)) ([5892989](https://github.com/tomag-9/zdravy-projekt/commit/5892989fa1ce42f82e6560ed4844dcc7c522a9af))
* implement stable viewport height hook and integrate into ClientLayout ([4de0413](https://github.com/tomag-9/zdravy-projekt/commit/4de0413e9ba3f8676928eae08e5fa516024916c1))
* Implement Traefik reverse proxy with Docker socket API rewrite ([1ef25a5](https://github.com/tomag-9/zdravy-projekt/commit/1ef25a56670a7305b713a66129961b535bb67af8))
* improve push notification reliability ([#292](https://github.com/tomag-9/zdravy-projekt/issues/292)) ([e4f6050](https://github.com/tomag-9/zdravy-projekt/commit/e4f605071872e073211885c8b4b379f3802b48a6))
* introduce services for report generation ([#110](https://github.com/tomag-9/zdravy-projekt/issues/110)) ([f12853f](https://github.com/tomag-9/zdravy-projekt/commit/f12853fa77a92461476309fda8eda7781111fe35))
* **katalóg:** úprava existujúceho rozloženia vrátane názvov zložiek ([f35e9fb](https://github.com/tomag-9/zdravy-projekt/commit/f35e9fbf6a4f5b3a9724b888a8228126f66454d9))
* klientova spätná väzba — písanie počtov, poradie diét, menu per chod, diéty v histórii ([0d4b11a](https://github.com/tomag-9/zdravy-projekt/commit/0d4b11af5ef913a102434f9b0e26f293c6ddd7ee))
* **logy:** audit vidí aj admin, systémové logy ostávajú superadminovi + retencia 7 dní ([2ce4f86](https://github.com/tomag-9/zdravy-projekt/commit/2ce4f860b896906465296877d42fa3e4b7396b05))
* medium fixes m1 m5 m7 m8 ([#289](https://github.com/tomag-9/zdravy-projekt/issues/289)) ([acc8f80](https://github.com/tomag-9/zdravy-projekt/commit/acc8f80426148b4b8f020d62ad3afa3de17d7cdb))
* **menu:** pridaj menu variant D ([#531](https://github.com/tomag-9/zdravy-projekt/issues/531)) ([9724293](https://github.com/tomag-9/zdravy-projekt/commit/9724293d7ae0275bc8e3c193a294b8492784459d))
* new UI + terraform + Edupage parseing v3.0 ([#370](https://github.com/tomag-9/zdravy-projekt/issues/370)) ([597a02c](https://github.com/tomag-9/zdravy-projekt/commit/597a02c9e2afa618f4c1cf24a64923a09721e57c))
* **notifications:** guarantee Inbox delivery + target-page allowlist ([bfafc4a](https://github.com/tomag-9/zdravy-projekt/commit/bfafc4a27aca041a5b894835da824c51677c5791))
* **objednavky:** audit log objednávok pre admina a superadmina ([f56e353](https://github.com/tomag-9/zdravy-projekt/commit/f56e35306134e6d983db857aed147d4b310fec4e))
* **objednavky:** frontend zamkne Menu B/C nad prísnym termínom, len znížiť sa dá ([49840db](https://github.com/tomag-9/zdravy-projekt/commit/49840db93be01f161204fb8f8c3e30280b12f6d1))
* **objednavky:** menu B a C max 2 dni vopred do 7:30 ([96ba65f](https://github.com/tomag-9/zdravy-projekt/commit/96ba65fd26c8309d9fef3c80e8822c4d6cebdea9))
* **objednavky:** nulova/zmazana objednavka trvalo zastavi auto-preklapanie ([6eb05f9](https://github.com/tomag-9/zdravy-projekt/commit/6eb05f968319d9a33a834177f2519f580830c43e))
* **objednavky:** odhlásenie Menu B/C povolené až do rána, nárast zostáva na 2-dňovom termíne ([83054a9](https://github.com/tomag-9/zdravy-projekt/commit/83054a94361ee836a02e5d65bbc99dca69fd77fa))
* **objednavky:** rovnaký Menu B/C strop aj pre celodennú objednávku ([43af1d8](https://github.com/tomag-9/zdravy-projekt/commit/43af1d86bd8e9b09ba47a16f0d72e8c78682df99))
* **observability:** debounce a reason label pre login-failure alerty ([2f30448](https://github.com/tomag-9/zdravy-projekt/commit/2f30448f75465dfd81a47a8b65d39ac536474428))
* **overload:** global request throttling, staggered push reminders, per-replica metrics ([ec19981](https://github.com/tomag-9/zdravy-projekt/commit/ec199816f88eaa2dd54538b8cc54210bb98ae4d4))
* **overload:** widen push-reminder lead time, retune CPU alert threshold ([5524d5c](https://github.com/tomag-9/zdravy-projekt/commit/5524d5c78ef223f15b2261af489a4faa49fe966e))
* **pack-separately:** pridaj druhú možnosť 'zabaliť zvlášť do GN' ([59dd8b9](https://github.com/tomag-9/zdravy-projekt/commit/59dd8b922e4983fa8b8fd32e8c02543b3bf298a6))
* pr1 client ux improvements ([#274](https://github.com/tomag-9/zdravy-projekt/issues/274)) ([1b2590d](https://github.com/tomag-9/zdravy-projekt/commit/1b2590d36cf0ea386d7eea56616be39d1d3a24d8))
* pr2 admin improvements ([#275](https://github.com/tomag-9/zdravy-projekt/issues/275)) ([2e4c887](https://github.com/tomag-9/zdravy-projekt/commit/2e4c887f135e2acaef391e368473d1956aad3db4))
* predškolák ako 1,25 porcie vo vyúčtovaní Edulienky ([#371](https://github.com/tomag-9/zdravy-projekt/issues/371)) ([ce3b0b0](https://github.com/tomag-9/zdravy-projekt/commit/ce3b0b06460e69fc903c3c242802709a611ff1d5))
* predškolák ako 1,25 porcie vo vyúčtovaní Edulienky ([#371](https://github.com/tomag-9/zdravy-projekt/issues/371)) ([b83134e](https://github.com/tomag-9/zdravy-projekt/commit/b83134e8a2cd2d36cbeee3fde3fd6a7864560242))
* **prevadzka:** obmedzenie menu na konkrétne dni v týždni (napr. menu B len v piatok) ([1511113](https://github.com/tomag-9/zdravy-projekt/commit/151111338d45f0db7d6927f265dd8e1d9190a437))
* **prevadzka:** stránkuj históriu objednávok v detaile prevádzky ([d7e7be7](https://github.com/tomag-9/zdravy-projekt/commit/d7e7be746d423bbe779ebda1b3c4dad0f5be9c8e))
* prod setups ([#324](https://github.com/tomag-9/zdravy-projekt/issues/324)) ([67a3984](https://github.com/tomag-9/zdravy-projekt/commit/67a3984fe82c0fd9c1399341f6ba04d46e1a5736))
* pwa ([#137](https://github.com/tomag-9/zdravy-projekt/issues/137)) ([cebfd62](https://github.com/tomag-9/zdravy-projekt/commit/cebfd621647c4a9dfec50a75601c44649dc3f434))
* pwa ([#137](https://github.com/tomag-9/zdravy-projekt/issues/137)) follow-ups ([f72fd8d](https://github.com/tomag-9/zdravy-projekt/commit/f72fd8da83ec7981bd16378c0fe0ce1f827b3fda))
* pwa enhancements ([#187](https://github.com/tomag-9/zdravy-projekt/issues/187)) ([06ca91e](https://github.com/tomag-9/zdravy-projekt/commit/06ca91e0fd3d0c5e80d787cddc48a9523a1cda1f))
* ranný EduPage scrape ručne tlačidlom namiesto cronu ([af097a2](https://github.com/tomag-9/zdravy-projekt/commit/af097a29ec54bab57e7b4a085a52340abe41ae37))
* refactor CI/CD workflows and enhance Redis configuration ([138c39b](https://github.com/tomag-9/zdravy-projekt/commit/138c39bc2674f45a011ec86ebdaa20850831441f))
* **release:** automated versioning via release-please + show app version in UI ([f93091f](https://github.com/tomag-9/zdravy-projekt/commit/f93091fad028b40b44dc32778f22a3f3a4ce1731))
* remove registration and resend verification pages ([#178](https://github.com/tomag-9/zdravy-projekt/issues/178)) ([8b7b1f2](https://github.com/tomag-9/zdravy-projekt/commit/8b7b1f2fe178e9eec10c5974bd463e39d97711b3))
* remove unused logo and favicon assets, update favicon references in HTML and Nginx config ([8b5974f](https://github.com/tomag-9/zdravy-projekt/commit/8b5974fc79a59863fb1bc5a349cd13663cf1e46a))
* replace username with email across the application ([#67](https://github.com/tomag-9/zdravy-projekt/issues/67)) ([1d32fd2](https://github.com/tomag-9/zdravy-projekt/commit/1d32fd2959c65e83ea319557acdb9728166925de))
* **reports:** add diet colors, pack-separately markers, PDF totals ([#418](https://github.com/tomag-9/zdravy-projekt/issues/418)) ([e1a337b](https://github.com/tomag-9/zdravy-projekt/commit/e1a337b1eee213229f550326865497902bc108c0))
* **reports:** denný report ako PDF prehľadu, pripravené na tlač A4 ([d09e9df](https://github.com/tomag-9/zdravy-projekt/commit/d09e9df3445d622c601bead161dc48a0ededc422))
* **reports:** denný report ako PDF prehľadu, pripravené na tlač A4 ([66c2bc9](https://github.com/tomag-9/zdravy-projekt/commit/66c2bc9c2fd6bd625b6a3a3029ff0397fefe94b1))
* **reports:** vypínač denných reportov a zreťazenie za EduPage scrape ([efbe685](https://github.com/tomag-9/zdravy-projekt/commit/efbe6858df7e373ae78eccf4860621f3f1814f97))
* rolový systém, kuchyňa, granulárne oprávnenia a voľno prevádzky ([#501](https://github.com/tomag-9/zdravy-projekt/issues/501)) ([b788bdf](https://github.com/tomag-9/zdravy-projekt/commit/b788bdf5543f029eedc87a00f55d8081d55478f8))
* **rozvoz:** premenovanie bloku a presun trasy medzi blokmi ([df0a4c7](https://github.com/tomag-9/zdravy-projekt/commit/df0a4c7aac0005177fd58675d58f60648e59817d))
* small edits ([#63](https://github.com/tomag-9/zdravy-projekt/issues/63)) ([8e51ae4](https://github.com/tomag-9/zdravy-projekt/commit/8e51ae40aad2e5f5eac66f0669423a206dbc8684))
* stav hesla loginu (success/pending/failed) + resend pozvánky ([b9a2fbf](https://github.com/tomag-9/zdravy-projekt/commit/b9a2fbf37ea878625b0244a8db2a46bc2d438c35))
* sync develop → main ([#563](https://github.com/tomag-9/zdravy-projekt/issues/563)) ([237208d](https://github.com/tomag-9/zdravy-projekt/commit/237208de996a0d91154706dcf33ea5069b5730b3))
* **tabuľka:** čitateľné trasy, pás jedál v hlavičke a stĺpec Poznámka ([4afffcd](https://github.com/tomag-9/zdravy-projekt/commit/4afffcd20c58294e2c38b326b01fd783c83fee85))
* **tabuľka:** tlač po výdajných bodoch a zrozumiteľnejší výber tlače ([2b98f6a](https://github.com/tomag-9/zdravy-projekt/commit/2b98f6a973db97ea6820c32daf4ebeb359987834))
* **ui:** zadávaj diéty ako samostatnú položku pod Menu A ([#468](https://github.com/tomag-9/zdravy-projekt/issues/468)) ([cfca6c3](https://github.com/tomag-9/zdravy-projekt/commit/cfca6c3e7f88ff7315f7fde9a7dd47e0118d2449))
* update main ([#334](https://github.com/tomag-9/zdravy-projekt/issues/334)) ([2ad2c26](https://github.com/tomag-9/zdravy-projekt/commit/2ad2c2692c88d7af44495baf356666449022448b))
* update main ([#336](https://github.com/tomag-9/zdravy-projekt/issues/336)) ([4bb2079](https://github.com/tomag-9/zdravy-projekt/commit/4bb2079aa34ceca1fbfc8d4a709005ce217b1880))
* **vydaj:** výdajný bod je vlastnosť prevádzky a delí tabuľku aj trasy ([56c30d9](https://github.com/tomag-9/zdravy-projekt/commit/56c30d95b4fa03aed36a85888f6cf0a0b7d8befa))


### Bug Fixes

* admin editor objednávok — koniec strate dát + parita s klientom ([72238a8](https://github.com/tomag-9/zdravy-projekt/commit/72238a839b02071d7dba8d3e9cedd4c87d85d7ab))
* **admin:** AdminDashboard testy čakajú, kým sa Nastavenia tabuľky odomknú (flaky v CI) ([9629ff3](https://github.com/tomag-9/zdravy-projekt/commit/9629ff34e823f3d404210d88061bf13a002f79e7))
* **admin:** AdminUserSerializer vracia skutočnú rolu, nie len is_staff fallback ([a0b9511](https://github.com/tomag-9/zdravy-projekt/commit/a0b95114ac0df3fdc33d8e1502cb07ba5e1370f2))
* **admin:** diet numbering in DietManager starts at 1, not 0 ([ae180ed](https://github.com/tomag-9/zdravy-projekt/commit/ae180edc93e8e589316a5215bba60c0a80eadf6b))
* **admin:** guard meal-template grams parsing against comma decimals / non-numeric input ([e4c2816](https://github.com/tomag-9/zdravy-projekt/commit/e4c281638413e0b9bae3f16d14680aac96460133))
* **admin:** guard meal-template grams parsing against comma decimals / non-numeric input ([9f61e3e](https://github.com/tomag-9/zdravy-projekt/commit/9f61e3e82bc416bf61ee43c8978728d15bb56c79))
* **admin:** improve diet colors and combinations ([32a09fa](https://github.com/tomag-9/zdravy-projekt/commit/32a09fa54d569e0b294eb3eb22d9a3e458d42fa6))
* **admin:** move day-lock UI from prevadzka-overview to dashboard ([c76eb4a](https://github.com/tomag-9/zdravy-projekt/commit/c76eb4a097ecba302d799c9600e950d65f7ab906))
* **admin:** poradie chodov v detaile prevádzky raňajky/obed/olovrant ([0dfd43a](https://github.com/tomag-9/zdravy-projekt/commit/0dfd43ad2bd13617d51ce7e90865b3533e66184e))
* **admin:** remove locked-day order PDF/XLSX report, unify dashboard exports ([7bef00e](https://github.com/tomag-9/zdravy-projekt/commit/7bef00ec5ae2b785bd91746d980f9cd1ccad8c78))
* api url ([#13](https://github.com/tomag-9/zdravy-projekt/issues/13)) ([f742f9a](https://github.com/tomag-9/zdravy-projekt/commit/f742f9a58005519bdcfcbf791125d279ae17eee9))
* **audit:** nezhoď uloženie profilu na poli s vnoreným source ([#481](https://github.com/tomag-9/zdravy-projekt/issues/481)) ([6017c39](https://github.com/tomag-9/zdravy-projekt/commit/6017c39e000091ba684ee47177b515bda3e55a5e))
* **audit:** nezhoď uloženie profilu na poli s vnoreným source ([#481](https://github.com/tomag-9/zdravy-projekt/issues/481)) ([44709dc](https://github.com/tomag-9/zdravy-projekt/commit/44709dcdc600f3012306d3557f96b78555579a95))
* **auto-objednavky:** rozdeľ auto-objednávku na behy podľa uzávierky ([#548](https://github.com/tomag-9/zdravy-projekt/issues/548)) ([f8acd78](https://github.com/tomag-9/zdravy-projekt/commit/f8acd7891b58a1de49f8743787d456d3f80cbf28))
* **backend:** add missing portion-summary bands and admin notes to gramage exports ([df528cd](https://github.com/tomag-9/zdravy-projekt/commit/df528cdabe48c497c5854dc08a1da401c1880212))
* **backend:** audit order gaps, readable diffs ([#432](https://github.com/tomag-9/zdravy-projekt/issues/432)) ([3c35ad8](https://github.com/tomag-9/zdravy-projekt/commit/3c35ad808da27816300494a7856c8ed279c546fb)), closes [#427](https://github.com/tomag-9/zdravy-projekt/issues/427)
* **backend:** enforce composite-diet nesting rule server-side ([9d554e8](https://github.com/tomag-9/zdravy-projekt/commit/9d554e8e48a476e9f1b6b776fe7cc78973113632))
* **backend:** fix Edulienka delivery seed reactivation ([#437](https://github.com/tomag-9/zdravy-projekt/issues/437)) ([b58d324](https://github.com/tomag-9/zdravy-projekt/commit/b58d324efff7b347caef922ab4262254f68e6989))
* **backend:** fix Edulienka seed split name mismatch ([#435](https://github.com/tomag-9/zdravy-projekt/issues/435)) ([09f31c4](https://github.com/tomag-9/zdravy-projekt/commit/09f31c43816e4f2f9c00a36ba75947de1e470380))
* **backend:** Montessori EduPage class mapping + split-facility olovrant bug ([f4abbf3](https://github.com/tomag-9/zdravy-projekt/commit/f4abbf32f91e04e1adada501dfc764c57f3bc1f2))
* **backend:** restore self-edit/null-target guard on order audit logging ([d2070df](https://github.com/tomag-9/zdravy-projekt/commit/d2070df368a7b8472090eda48d744c10dd8e3197))
* **backend:** stop settings lookup from clobbering requested prevadzka list ([d07d15a](https://github.com/tomag-9/zdravy-projekt/commit/d07d15a4000b81424430c83e66b5d656cb1bf674))
* **backend:** unblock deletes from legacy relations ([de9c141](https://github.com/tomag-9/zdravy-projekt/commit/de9c14103416ca0525feb2feb3ada3f3c02fb2b8))
* **backend:** unblock deletes from legacy relations ([79affce](https://github.com/tomag-9/zdravy-projekt/commit/79affce1b1cc25ee7adca67704759f87b4d29906))
* **backend:** update stale diet_summary_rows assertion for diet colors ([8bf2379](https://github.com/tomag-9/zdravy-projekt/commit/8bf2379db8ea06acb97e7413d0e7fdf3db17b0af))
* **cache:** invaliduj gramage dashboard cache pri uzavretí dňa, deadline a EduPage scrape ([e33251d](https://github.com/tomag-9/zdravy-projekt/commit/e33251df1166cdfcd99afffe22e657c2d24ec2ea))
* **ci:** align cleanup tests with protected history ([df05110](https://github.com/tomag-9/zdravy-projekt/commit/df05110650e7b7f10dabf87b44e14cd7fddafbae))
* **ci:** drop org_id from grafana_rule_group ([#405](https://github.com/tomag-9/zdravy-projekt/issues/405)) ([9f9c815](https://github.com/tomag-9/zdravy-projekt/commit/9f9c81563bc7228a203a8b8f1de8cbd35c95e1c4))
* **ci:** drop org_id from grafana_rule_group, API keys are org-scoped ([79dd545](https://github.com/tomag-9/zdravy-projekt/commit/79dd545ff80efcca41498f88ed0ac102e2e2526a))
* client view site ([#22](https://github.com/tomag-9/zdravy-projekt/issues/22)) ([ce35d38](https://github.com/tomag-9/zdravy-projekt/commit/ce35d38a7626ccd2138bceab79fd07bdd43ad703))
* **closed-days:** closed_by nesmie blokovať mazanie loginu (PROTECT -&gt; SET_NULL) ([67a78cd](https://github.com/tomag-9/zdravy-projekt/commit/67a78cd43ea44979ebae7a6cfae4e8ac81744203))
* **code-review:** oprav nálezy z 5-dňového code review (2026-08-31) ([#555](https://github.com/tomag-9/zdravy-projekt/issues/555)) ([65e5bdf](https://github.com/tomag-9/zdravy-projekt/commit/65e5bdf45343c85f9a21d6eb2dcab8f48a3d2c76))
* **cron:** úlohy s deadlinom deň vopred spúšťaj v predvečer, nie Po–Pi ([d41fee8](https://github.com/tomag-9/zdravy-projekt/commit/d41fee8efff6e5739967426e7f8a9721b8c94435))
* **cron:** úlohy s deadlinom deň vopred spúšťaj v predvečer, nie Po–Pi ([cc597a4](https://github.com/tomag-9/zdravy-projekt/commit/cc597a40858508de37896453d4e4a0b284ffef0f))
* **cron:** vyhodnocuj skip-check voci cielovemu dnu, nie dnesku ([6707cc8](https://github.com/tomag-9/zdravy-projekt/commit/6707cc838be150c0cb65e2e9a8286a176c0b18e3))
* **dashboard:** zajtrajšok sa odomkne o 12:00, ale ako predvolený deň naskočí až o 21:00 ([04fb902](https://github.com/tomag-9/zdravy-projekt/commit/04fb902b8b59f683d834284d52be98fb2864cb45))
* **db:** default retained legacy columns ([d646ba2](https://github.com/tomag-9/zdravy-projekt/commit/d646ba2ab0233fa383d9b31164ed107d2fe33fd8))
* **db:** default retained legacy columns ([71ca772](https://github.com/tomag-9/zdravy-projekt/commit/71ca77233b19e2e2c6682e8f6694a4cc0d83a97f))
* **db:** keep contract migrations rolling-safe ([635a702](https://github.com/tomag-9/zdravy-projekt/commit/635a702d509187f200006b3242222366e00d0788))
* **db:** keep contract migrations rolling-safe ([981c005](https://github.com/tomag-9/zdravy-projekt/commit/981c0052058ac868b8ad0b6006f9caedb769a4f0))
* **db:** preserve facility data during refactor ([f223d8a](https://github.com/tomag-9/zdravy-projekt/commit/f223d8a8ddb6fc8a727e880cf68e757b94f4da22))
* **deploy:** drop unenforced prod guard from seed_real_delivery_layout ([3cac441](https://github.com/tomag-9/zdravy-projekt/commit/3cac4417f5bfaaa1a45f00b2c0663e2adfb8c5c0))
* **docs:** update commit and PR guidelines in CLAUDE.md ([b3eba91](https://github.com/tomag-9/zdravy-projekt/commit/b3eba912d52108c51796c7768cd48eb442a8bd05))
* EduPage facility reconciliation and modal focus ([#373](https://github.com/tomag-9/zdravy-projekt/issues/373)) ([73f9252](https://github.com/tomag-9/zdravy-projekt/commit/73f9252bcf76416258aed4fb334d83d372bce6f8))
* EduPage facility reconciliation and modal focus ([#373](https://github.com/tomag-9/zdravy-projekt/issues/373)) ([4641266](https://github.com/tomag-9/zdravy-projekt/commit/46412669194a7bb1e909a7e9ce428a421ce6c112))
* EduPage prevádzky bez auto-objednávok + ranný scrape o 8:00 ([86f31c9](https://github.com/tomag-9/zdravy-projekt/commit/86f31c93f67432c24ccdc935d773b8a5c8dabe45))
* **edupage:** 'Klasik B' sa počítalo ako Menu A, nie Menu B ([1c9bb8a](https://github.com/tomag-9/zdravy-projekt/commit/1c9bb8aa5ba9483d9a21abac846a0093d2db8104))
* **edupage:** British School — celý deň sa zlieval do jedného 'obeda' ([e149984](https://github.com/tomag-9/zdravy-projekt/commit/e14998400d8fb779de925f7555866e929bf31d2c))
* **edupage:** British School routing + preklad diét do slovenčiny ([#531](https://github.com/tomag-9/zdravy-projekt/issues/531)) ([dfe4d2b](https://github.com/tomag-9/zdravy-projekt/commit/dfe4d2b59b622a53c7e65234c6f115757abeff3f))
* **edupage:** British School učitelia (porcia=5) dostávali MŠ porcie namiesto dospelých ([aa06508](https://github.com/tomag-9/zdravy-projekt/commit/aa0650884b59ad5946cb874298319c72897d7f6f))
* **edupage:** CMŠ Pezinok skratka 'H' (Hlavná budova) sa nemá počítať ([0bfa009](https://github.com/tomag-9/zdravy-projekt/commit/0bfa009164651d546a1d3038d7acb83a51b6ea91))
* **edupage:** cron skip má sledovať cieľový dátum jedla, nie dnešok ([#518](https://github.com/tomag-9/zdravy-projekt/issues/518)) ([863315a](https://github.com/tomag-9/zdravy-projekt/commit/863315aa21ace270ad3a99471b15514c696753d0))
* **edupage:** doplň 3 uncertain fuzzy-match skratky na isté diéty (Felix, Filipáneriho, Rozmanitá) ([e3c4e65](https://github.com/tomag-9/zdravy-projekt/commit/e3c4e650f5c34321ee3481142acd5c4171f90024))
* **edupage:** exclude Rozmanita Škola from EduPage connection in seed command ([d589201](https://github.com/tomag-9/zdravy-projekt/commit/d5892019912a73be3ba320528a431fdc47faaaef))
* **edupage:** Filipáneriho NNNO preventívne + Ivanka nejednoznačná NMNGnORECH skratka ([6079029](https://github.com/tomag-9/zdravy-projekt/commit/607902942275278b515349765e7ad5f56957a7c3))
* **edupage:** flaguj neisté fuzzy priradenie diéty, zobraz ho v prehľade ([#527](https://github.com/tomag-9/zdravy-projekt/issues/527), [#528](https://github.com/tomag-9/zdravy-projekt/issues/528)) ([2709564](https://github.com/tomag-9/zdravy-projekt/commit/2709564c4a5c4993f1b2bb0e74ba08be8633a946))
* **edupage:** Krásňanko DNM/PDNM/Z1/2NM potvrdené na isté pravidlá ([b051a38](https://github.com/tomag-9/zdravy-projekt/commit/b051a38ba2cb8e8241975e473994caf5c3de61fc))
* **edupage:** Krásňanko DNM/PDNM/Z1/2NM potvrdené na isté pravidlá ([093ebdf](https://github.com/tomag-9/zdravy-projekt/commit/093ebdfed6ced8407d2891b0c5bec694365bfcf5))
* **edupage:** letter_hook pre nové kombinované diéty ([#527](https://github.com/tomag-9/zdravy-projekt/issues/527)) ([5e85d87](https://github.com/tomag-9/zdravy-projekt/commit/5e85d873eff1d183b33c6d865d7463790d9279a8))
* **edupage:** Libellus NENO -&gt; NO EGG - NO ORECH (pk 124) ([b3ba764](https://github.com/tomag-9/zdravy-projekt/commit/b3ba7647a95b6e145ff683be7b26527b8163dff7))
* **edupage:** Montessori nMnGnE skratka s bodkami na okrajoch nesadla na letter_hook kľúč ([b72f63f](https://github.com/tomag-9/zdravy-projekt/commit/b72f63fb7c22a6a2fa3aeee3c440f01913a7baaf))
* **edupage:** Montessori z EduPage počíta výhradne 'Iná' skupinu ([a95a93b](https://github.com/tomag-9/zdravy-projekt/commit/a95a93babcff0bc87040c628213e2dea8faddf7e))
* **edupage:** nahlás olovrant/raňajky drift aj per-prevádzka, nie len merged ([183577a](https://github.com/tomag-9/zdravy-projekt/commit/183577a79e74fdb1201bd72077f12e5ce500f0c0))
* **edupage:** odstráň manual-review flag zo zšlaNMnEnOnJ, diéta je potvrdená ([369a193](https://github.com/tomag-9/zdravy-projekt/commit/369a19308ffe922a61fabdb2fd8206cd08e8fa26))
* **edupage:** oprav 3 potvrdené nesprávne diétne mapovania (Cvernička, Felix Karlovská, Zdravé Brúško) ([#534](https://github.com/tomag-9/zdravy-projekt/issues/534)) ([e93358b](https://github.com/tomag-9/zdravy-projekt/commit/e93358be72c52c3730698cbe802f5fe85e28907d))
* **edupage:** oprav názov celku Školička ZŠ v seed_skolicka_zs_2026_09 ([4ee2273](https://github.com/tomag-9/zdravy-projekt/commit/4ee22734d9a1fd947ba89775d20a2a9030814835))
* **edupage:** potvrď NMNGnORECH a nGH na isté diéty (ZŠ Ivanka, MŠ Edulienka) ([09be282](https://github.com/tomag-9/zdravy-projekt/commit/09be2820d3b8791727ffcc9c659d43bcdbf1ed24))
* **edupage:** potvrď olovrant_mode=EDUPAGE pre ZŠ Ivanka pri Dunaji ([398738a](https://github.com/tomag-9/zdravy-projekt/commit/398738af2197d55a7e697e398dde64e01f8b5d0d))
* **edupage:** potvrď uncertain diéty na isté pravidlá, oprav Montessori a logging bug ([0cad6a8](https://github.com/tomag-9/zdravy-projekt/commit/0cad6a8bccd360fac40ff2020f664a0589f0eba4))
* **edupage:** potvrď uncertain diéty na isté pravidlá, oprav Montessori a logging bug ([c28798b](https://github.com/tomag-9/zdravy-projekt/commit/c28798b54e979732e9de8684a1baeb3db85939b5))
* **edupage:** predbežný Menu B/C scrape nesmie spustiť plný chained report ([ff443c1](https://github.com/tomag-9/zdravy-projekt/commit/ff443c1b7cbdb29c78168f1c50bb57809b8734f7))
* **edupage:** pridaj EduPage prepojenie pre Školičku ZŠ ([7badd1d](https://github.com/tomag-9/zdravy-projekt/commit/7badd1da6ec874e6846f72beda3fdfaa4a7e4955))
* **edupage:** rozdeľ Rozmanitú na MŠ/ZŠ, dospelých priraď škole ([6209c6f](https://github.com/tomag-9/zdravy-projekt/commit/6209c6f189567f9df8a826cc15c176845963a295))
* **edupage:** rozpoznaj 'citrus' ako diétny signál (MŠ Rozmanitá) ([280abe1](https://github.com/tomag-9/zdravy-projekt/commit/280abe1cd5126e914081f2722e8508d2ca8a854d))
* **edupage:** Školička ŠPECI diéta chodí ako menu písmeno, nie payer ([c07f047](https://github.com/tomag-9/zdravy-projekt/commit/c07f047ad5373356612c5a9ce44c137212382b5a))
* **edupage:** Školička ZŠ BM/NM/H diéty, Mal./Hey. raňajky/olovrant payer-priority fix ([882c9b6](https://github.com/tomag-9/zdravy-projekt/commit/882c9b61b46c434f17d9fbacb82a12274c197ff8))
* **edupage:** SŠV payer group už nevynucuje VEGGIE pre všetky objednávky ([71a6831](https://github.com/tomag-9/zdravy-projekt/commit/71a6831ba5cb124cea16c53b33d7debef514923f))
* **edupage:** učiteľ/dospelí v Školičke ZŠ sa počítajú pod 2. stupňom ([f42a60b](https://github.com/tomag-9/zdravy-projekt/commit/f42a60b7a7870241176f23ab56340e18ffdc21a9))
* **edupage:** zosuladi letter_hook nazvy s realne zalozenymi Diet zaznamami ([3437d20](https://github.com/tomag-9/zdravy-projekt/commit/3437d20028a0c593bcd5d0e90cae16efa2236657))
* emails ([#73](https://github.com/tomag-9/zdravy-projekt/issues/73)) ([76f9d2f](https://github.com/tomag-9/zdravy-projekt/commit/76f9d2fb443d1c047c03df300c542e93d3241f44))
* escape nginx vars in staging compose configs block ([#21](https://github.com/tomag-9/zdravy-projekt/issues/21)) ([4b6055f](https://github.com/tomag-9/zdravy-projekt/commit/4b6055f5a3800ce143cd20898f2e15c833c871cc))
* exclude Rozmanita Škola from EduPage connection in seed command ([66140d6](https://github.com/tomag-9/zdravy-projekt/commit/66140d65ff023133c42d667b6cc6729dd2532c80))
* exempt /metrics/ from HTTPS redirect for Alloy scraping ([06e93f7](https://github.com/tomag-9/zdravy-projekt/commit/06e93f71f522054e4892d2a98332f7fd87595f5d))
* few fixes ([#112](https://github.com/tomag-9/zdravy-projekt/issues/112)) ([0240c3d](https://github.com/tomag-9/zdravy-projekt/commit/0240c3d60512bed1b06e0ae231eb854f096411ac))
* few fixes ([#68](https://github.com/tomag-9/zdravy-projekt/issues/68)) ([08ee7f7](https://github.com/tomag-9/zdravy-projekt/commit/08ee7f7e5f9e4d1bc375828f319063ec34726a2e))
* few fixes 1 ([#106](https://github.com/tomag-9/zdravy-projekt/issues/106)) ([6cfee71](https://github.com/tomag-9/zdravy-projekt/commit/6cfee718b1d99778c240e56da1f96bc2796e8268))
* few minor fixes ([#46](https://github.com/tomag-9/zdravy-projekt/issues/46)) ([2be7326](https://github.com/tomag-9/zdravy-projekt/commit/2be7326cc1c930a3ee887503f2e8a1a31fea2d8b))
* finish low review fixes ([#291](https://github.com/tomag-9/zdravy-projekt/issues/291)) ([06bcf8c](https://github.com/tomag-9/zdravy-projekt/commit/06bcf8c463743fe23808c8d05a74b19ee9027ed8))
* fix-trigers and added frontend tests ([2bff6a6](https://github.com/tomag-9/zdravy-projekt/commit/2bff6a6cfe95bddb2b28ea892d094258988a0dfc))
* fowarding ([#14](https://github.com/tomag-9/zdravy-projekt/issues/14)) ([7341472](https://github.com/tomag-9/zdravy-projekt/commit/734147279c598f7b6bf64e7045a2da4303378918))
* **frontend:** guard date-scoped fetch effects against stale responses ([59cf31a](https://github.com/tomag-9/zdravy-projekt/commit/59cf31a3fcc8e27f719a224f1264183053e479fd))
* **frontend:** login mgmt, mobile keyboard fix, tour cleanup ([#431](https://github.com/tomag-9/zdravy-projekt/issues/431)) ([0c85a21](https://github.com/tomag-9/zdravy-projekt/commit/0c85a214379f8337f99d97b1aec0b59c3bbf8df5))
* **frontend:** tour tooltip positioning + PWA banner overlap ([#436](https://github.com/tomag-9/zdravy-projekt/issues/436)) ([5f77cc0](https://github.com/tomag-9/zdravy-projekt/commit/5f77cc0dc65071537e0c4ebb59eb61cc060fcad6))
* give backend a hyphen-only network alias for Alloy metrics scraping ([7b78350](https://github.com/tomag-9/zdravy-projekt/commit/7b78350127fcde0b98452096bd084d4316567506))
* **gramaz:** hlavny udaj sumaru porcii ukazoval iba MS porcie, zvysok '—' ([#529](https://github.com/tomag-9/zdravy-projekt/issues/529)) ([ef958c5](https://github.com/tomag-9/zdravy-projekt/commit/ef958c5d42ceb5f712d2051c559cb354a8f4bf9a))
* **gramaz:** nezdvojuj polievku pri porcii balenej celá 'zvlášť' ([ac560ec](https://github.com/tomag-9/zdravy-projekt/commit/ac560ecdde0803223aead7317f8a3ee5ca676280))
* **gramaz:** poznámka prevádzky ide hneď za názov, nie do úzkeho stĺpca Poznámka ([32d3ff7](https://github.com/tomag-9/zdravy-projekt/commit/32d3ff7551f0b84d5ce7225bc69c572953583ade))
* **gramaz:** vlastny multi-select dropdown pre cluster filter ([cff2b32](https://github.com/tomag-9/zdravy-projekt/commit/cff2b326d57e55cc0582ad146984350cad21071e))
* **gramaz:** zabaliť zvlášť nezobrazuje duplicitný čistý riadok ([2dd5396](https://github.com/tomag-9/zdravy-projekt/commit/2dd5396d524309bbca26b096bb5725f2e985c302))
* **gramaz:** žltá pri 'Olovrant ide s obedom' zmizla v riadku 'Súčet bez diét' ([82c4eb1](https://github.com/tomag-9/zdravy-projekt/commit/82c4eb1ad661f64f00be91966e57494eff07a510))
* H2, H3 , H4 ([#277](https://github.com/tomag-9/zdravy-projekt/issues/277)) ([b1b8c69](https://github.com/tomag-9/zdravy-projekt/commit/b1b8c692da3a8baecd2e1f1d1a20ebee5207d6a2))
* **heslo:** zrozumiteľné hlášky pri nastavovaní hesla ([85d4e4b](https://github.com/tomag-9/zdravy-projekt/commit/85d4e4b5b843f8eeb50bb5caf3584e6cead12176))
* **heslo:** zrozumiteľné hlášky pri nastavovaní hesla ([dbccbc2](https://github.com/tomag-9/zdravy-projekt/commit/dbccbc26f4e983a5c72059c66c88ec0a73b1b7a4))
* hotfix apis ([#144](https://github.com/tomag-9/zdravy-projekt/issues/144)) ([b3d84b5](https://github.com/tomag-9/zdravy-projekt/commit/b3d84b52057f038965bf489a996ddd688fda6e43))
* immutable production tags ([#372](https://github.com/tomag-9/zdravy-projekt/issues/372)) ([9a8ff66](https://github.com/tomag-9/zdravy-projekt/commit/9a8ff666fab55817be583e123463cb189ec156c4))
* immutable production tags ([#372](https://github.com/tomag-9/zdravy-projekt/issues/372)) ([6ac0688](https://github.com/tomag-9/zdravy-projekt/commit/6ac068825cae31a18432f693600dfbb1ea939b44))
* init throwaway backend for Grafana plan step ([21bbd78](https://github.com/tomag-9/zdravy-projekt/commit/21bbd789d2b24676b872370bf72eda91493c2706))
* load complete paginated lists ([4d20514](https://github.com/tomag-9/zdravy-projekt/commit/4d205141f3ba49b79b3bf7e0f02427fac73ef715))
* **load-tests:** seed_load_test_users cleanup neuvoľňoval Celok/Prevadzka ([b88bea0](https://github.com/tomag-9/zdravy-projekt/commit/b88bea03504447cc032450245a6c6d4ad2da5b2b))
* **loginy:** zmaž klientský login, ak zmazanie celku/prevádzky vezme posledný prístup ([74d179c](https://github.com/tomag-9/zdravy-projekt/commit/74d179cb0c2a934ee97ab66355010537ae94a324))
* **logy:** objednávky iba v Objednávky, presné časy a uzávierky v Nadchádzajúcich ([7efb3d8](https://github.com/tomag-9/zdravy-projekt/commit/7efb3d8673c63f07dc0330529267010592886130))
* make production compose image tags stack-compatible ([f2b1504](https://github.com/tomag-9/zdravy-projekt/commit/f2b15048729b1b3c72addabe01511836777194d2))
* make production compose image tags stack-compatible ([205c8cf](https://github.com/tomag-9/zdravy-projekt/commit/205c8cf1b36b3071f031f9665a421fb0c1a4d402))
* manuálne odoslanie cez auto objednávku nevynuluje is_auto ([3e08e41](https://github.com/tomag-9/zdravy-projekt/commit/3e08e4165d8792d151b57be30d15191e442c841d)), closes [#507](https://github.com/tomag-9/zdravy-projekt/issues/507)
* mix small fixes ([#81](https://github.com/tomag-9/zdravy-projekt/issues/81)) ([ded3f98](https://github.com/tomag-9/zdravy-projekt/commit/ded3f9819443d5cb419653e2207bc73dcf3d3cd2))
* **nadchadzajuce:** Najbližší beh sedí s časom v popise, nie posunutý o UTC offset ([1dd0ac9](https://github.com/tomag-9/zdravy-projekt/commit/1dd0ac98b743ddd342236f6d2d8d6bca8ec287b3))
* **objednavky:** admin-zapísaná objednávka sa preklopí auto-orderom aj bez klienta ([0e45208](https://github.com/tomag-9/zdravy-projekt/commit/0e45208fdada543f3ca2bacec3f0ac6aa5b0b440))
* **objednavky:** loguj zamietnutie objednávky, presnejšia hláška, Menu D pod prísnejší termín ([7b7fdb7](https://github.com/tomag-9/zdravy-projekt/commit/7b7fdb74883abf142634d7f9a98b103f7f92a6f3))
* **objednavky:** vynúť menu_day_restrictions aj v admin editore a na backende ([474c996](https://github.com/tomag-9/zdravy-projekt/commit/474c9969e6493986e2b8ef8f0be1cbf5e06b7dce))
* **objednavky:** vyžaduj poznámku pri diéte 'Špeciálna' aj na backende ([3702323](https://github.com/tomag-9/zdravy-projekt/commit/3702323f22a4c81723e17d256a3a60c96741744c))
* oddeľovacia čiara aj medzi Olovrantom a Poznámkou ([#503](https://github.com/tomag-9/zdravy-projekt/issues/503)) ([5a92736](https://github.com/tomag-9/zdravy-projekt/commit/5a927368d89dc1b673ea10a180736e8f7fc08d4a))
* optimize saving of visible menus and meals in ClientSettings ([03df863](https://github.com/tomag-9/zdravy-projekt/commit/03df863620395902010b394cedef8b60d9257a35))
* optimize saving of visible menus and meals in ClientSettings ([8142a41](https://github.com/tomag-9/zdravy-projekt/commit/8142a4154338691500290cf765140ce095c232e7))
* **order:** nedovoľ zakázanú veľkosť porcie a vráť hlavičku prevádzky bez objednávky ([39c309a](https://github.com/tomag-9/zdravy-projekt/commit/39c309a9f6f569d5b600e731bbc6c6cf8bf46378))
* **orders:** don't let a reshaped-but-unchanged locked meal block other meals ([accdf64](https://github.com/tomag-9/zdravy-projekt/commit/accdf64e1fed24411c9fbc11c1f88a86a48d4dd0))
* **orders:** nezahadzuj vlastné názvy diét pri načítaní objednávky ([f7a6d4d](https://github.com/tomag-9/zdravy-projekt/commit/f7a6d4ddd3e46cb0c367ac6bed2bb9f9a867eaa8))
* **orders:** počítaj naplánované dni a súhrn za celý celok ([1abfa09](https://github.com/tomag-9/zdravy-projekt/commit/1abfa09fae39f4b4cdbc2dd7f99e51bb71de4519))
* **orders:** prijmi special_diet_note a pošli prevádzku z home ([60a3e8d](https://github.com/tomag-9/zdravy-projekt/commit/60a3e8de5cdbf39707e829a2abb2aa724256fc00))
* **orders:** umožni prepnúť prevádzku po prvom výbere ([9e36cd2](https://github.com/tomag-9/zdravy-projekt/commit/9e36cd2145ad6d3092c9c55b0f6c039b4c13da7c))
* **order:** zobraziť aj diétu chýbajúcu v enabledDiets v DietSelector ([757f196](https://github.com/tomag-9/zdravy-projekt/commit/757f19604454f4561d955be7f0dfa1daf7531946))
* **pdf:** gramáž — vynechať 'Súčet bez diét' a diétne súhrny v PDF ([15011fe](https://github.com/tomag-9/zdravy-projekt/commit/15011fe10899bbc89b2cb107681bb50505b9398c)), closes [#510](https://github.com/tomag-9/zdravy-projekt/issues/510)
* poznamka prevadzky v stlpci Poznamka aj na zbalenom riadku klienta ([40d66dd](https://github.com/tomag-9/zdravy-projekt/commit/40d66ddf705498089286595f0a53d5c383661194)), closes [#513](https://github.com/tomag-9/zdravy-projekt/issues/513)
* Pramienok celodenka — olovrant sa vždy odvodí z obeda ([a17fb41](https://github.com/tomag-9/zdravy-projekt/commit/a17fb417e7b4391912f122412a17f643b8913ba8))
* **prevadzka:** nezresetuj admin nastavené visible_menus/meals pri seede; doplň Špeciálnu diétu v admin editore a jej poznámku do gramážovej tabuľky ([5554b13](https://github.com/tomag-9/zdravy-projekt/commit/5554b1365879e279ef1aa8993619de60cd48fc27))
* **pristupy:** admin smie spravovať klientsky login, nie len superadmin ([9d3d09a](https://github.com/tomag-9/zdravy-projekt/commit/9d3d09a55e7600e3825a83ae9164622bc2ebd7c9))
* pwa logged ([#184](https://github.com/tomag-9/zdravy-projekt/issues/184)) ([b565327](https://github.com/tomag-9/zdravy-projekt/commit/b5653276542edafecbeab575f15284c0c36cd754))
* ranný scrape sa nespustí po uzávierke ([b57d8a6](https://github.com/tomag-9/zdravy-projekt/commit/b57d8a6b9092f1d74c0c7d1ebe21832a013c26cf))
* redirect2 ([#16](https://github.com/tomag-9/zdravy-projekt/issues/16)) ([0bab840](https://github.com/tomag-9/zdravy-projekt/commit/0bab840f002d6a4f420ca16c2eb5f9b1bef876c9))
* **reports:** apply client billing overrides to olovrant reporting ([c10c617](https://github.com/tomag-9/zdravy-projekt/commit/c10c617c7324bcceac5016fe41a46a005dba91e3))
* **reports:** posuň denné reporty 10 min za scrape ([2912bbb](https://github.com/tomag-9/zdravy-projekt/commit/2912bbbfd3baa2c7fcb6f67507db1b4740329b64))
* **reports:** posuň denné reporty 10 min za scrape ([4364a17](https://github.com/tomag-9/zdravy-projekt/commit/4364a17b9c8310e69bd11af58a66cc18a0feefb9))
* resolve CodeQL alert findings ([#309](https://github.com/tomag-9/zdravy-projekt/issues/309)) ([9c74528](https://github.com/tomag-9/zdravy-projekt/commit/9c74528f0b85b09c3f353b548ff17d11813a3080))
* resolve number 420 review findings ([#421](https://github.com/tomag-9/zdravy-projekt/issues/421)) ([d0a7bdd](https://github.com/tomag-9/zdravy-projekt/commit/d0a7bdde4aba9820c03422cb1fa2f754de11446b))
* return 401 (not 403) for auth failures ([#293](https://github.com/tomag-9/zdravy-projekt/issues/293)) ([3428ea0](https://github.com/tomag-9/zdravy-projekt/commit/3428ea039c68a4ab12e558c7f1df39bcf2e6981c))
* **scrape:** spúšťaj Edupage import presne v čase deadlinu ([92b0d92](https://github.com/tomag-9/zdravy-projekt/commit/92b0d9297fb3698ccc15708d025f38575996f250))
* **scrape:** spúšťaj Edupage import presne v čase deadlinu ([9b6756b](https://github.com/tomag-9/zdravy-projekt/commit/9b6756b4486f71e2d03004a6caf2357dbedb3219))
* **seed,diety:** odstráň zdroj Waldorf/Walldom duplicity a diét bez sort_order ([4d4fb44](https://github.com/tomag-9/zdravy-projekt/commit/4d4fb444232d5048e971ee7ce642faedafe48956))
* **seed:** Krásňanko mealsGuest link vypršal, nahraď novým ([0213322](https://github.com/tomag-9/zdravy-projekt/commit/0213322389b922d454d3ae0fc43a1e589aa58f1d))
* **seed:** nespadni na duplicitnom názve šablóny jedla ([99903a1](https://github.com/tomag-9/zdravy-projekt/commit/99903a14984f2ca7a366ae59eafe92f7eafe1ec2))
* **seed:** nespadni na duplicitnom názve šablóny jedla ([60f8b49](https://github.com/tomag-9/zdravy-projekt/commit/60f8b4913aa1e250e6d79ab6145133835ca8ff7c))
* **seed:** reconcile Celok merges/deletes with prod cleanup 2026-08-11 ([6ca10b5](https://github.com/tomag-9/zdravy-projekt/commit/6ca10b501fe26ad4b06c89af768d869421889b6d))
* set explicit allValue for dashboard variable ([#342](https://github.com/tomag-9/zdravy-projekt/issues/342)) ([00fca81](https://github.com/tomag-9/zdravy-projekt/commit/00fca81c48e07682b9f3f40a87d8a6abc2492506))
* set user agent for Dokploy API deploy ([653fc0e](https://github.com/tomag-9/zdravy-projekt/commit/653fc0ee20476ee912807e1348640d6c815503f8))
* set user agent for Dokploy API deploy ([4972b39](https://github.com/tomag-9/zdravy-projekt/commit/4972b3967002edd3d888b2637511de6c275879b4))
* show all admins in production UI ([#422](https://github.com/tomag-9/zdravy-projekt/issues/422)) ([509e984](https://github.com/tomag-9/zdravy-projekt/commit/509e984a62fadfca7cee11c5aba49e5f23409704))
* show all diets in admin UI ([#423](https://github.com/tomag-9/zdravy-projekt/issues/423)) ([a904d6d](https://github.com/tomag-9/zdravy-projekt/commit/a904d6d8ecbe2c2db64648f905e5d6a81694be4b))
* simplify service dependency declaration for backend in prod and staging configurations ([068cdbc](https://github.com/tomag-9/zdravy-projekt/commit/068cdbc7f8cc67ed0d31b63ac0a4d8a2bfd8b243))
* split production backfill migration transaction ([7c441f5](https://github.com/tomag-9/zdravy-projekt/commit/7c441f50c0939d5e8a32a50d1c0ff0d991720ee7))
* split production backfill migration transaction ([e760409](https://github.com/tomag-9/zdravy-projekt/commit/e7604099cacaab900cfe592a4ff8e54a434f40ba))
* stabilize staging routing and diet visibility ([#134](https://github.com/tomag-9/zdravy-projekt/issues/134)) ([75446c5](https://github.com/tomag-9/zdravy-projekt/commit/75446c5f193da84d463a92d7f930f2927bf7bd33))
* stagging redirect ([#15](https://github.com/tomag-9/zdravy-projekt/issues/15)) ([fd9c43a](https://github.com/tomag-9/zdravy-projekt/commit/fd9c43a5985b4b4f640bf84cbdcce16c3ea705cf))
* sub-prevádzky dedia EduPage pripojenie po splite ([#413](https://github.com/tomag-9/zdravy-projekt/issues/413)) ([abcae60](https://github.com/tomag-9/zdravy-projekt/commit/abcae60336885dda72b91a08de3b385127a6f05e))
* symmetric shared-storage bug in diet-remainder pack-separately row ([af2f104](https://github.com/tomag-9/zdravy-projekt/commit/af2f1048b6768919f3a1a6c93784d82056782b26))
* sync facility data to celok ([2a0cb95](https://github.com/tomag-9/zdravy-projekt/commit/2a0cb950e01de406b7a9d33c395670528ca9a80a))
* **tests:** correct stale assertions after [#416](https://github.com/tomag-9/zdravy-projekt/issues/416) portion-type prefetch ([64c0f69](https://github.com/tomag-9/zdravy-projekt/commit/64c0f69bd050a8277b1a545c4ff69f175a99d02d))
* tolerate whitespace in Dokploy API key ([94c8f6a](https://github.com/tomag-9/zdravy-projekt/commit/94c8f6a0b95d7a4d3b5abaea5b91c869472b1cc7))
* tolerate whitespace in Dokploy API key ([11fd69d](https://github.com/tomag-9/zdravy-projekt/commit/11fd69d22dfde728949b0ca686fce0516824f51f))
* **tour:** krok pre výber prevádzky a oprava pozicionovania tooltipu ([6a725df](https://github.com/tomag-9/zdravy-projekt/commit/6a725dfd6138264202dd385a223215837d90c59e))
* **tour:** neukazuj nový krok na pozícii toho predošlého ([251c84e](https://github.com/tomag-9/zdravy-projekt/commit/251c84edf2556a1bbe54d0ef7e8528980a168bbf))
* traefik router rules in staging configuration ([#133](https://github.com/tomag-9/zdravy-projekt/issues/133)) ([5f333f9](https://github.com/tomag-9/zdravy-projekt/commit/5f333f9c7333fa3cfd8dffade8ca18320c525d4c))
* update healthcheck command  ([#71](https://github.com/tomag-9/zdravy-projekt/issues/71)) ([d4cc420](https://github.com/tomag-9/zdravy-projekt/commit/d4cc420057c324c7b0c124730011bcdb756f140f))
* update nginx configuration for dynamic upstream resolution ([78932cc](https://github.com/tomag-9/zdravy-projekt/commit/78932cc38fcad560919106ea082e6eac3ae7a40a))
* use Compose's implicit backend alias instead of custom network alias ([b1dcc33](https://github.com/tomag-9/zdravy-projekt/commit/b1dcc33453afff2b7a03af4dfcf7c8e22e22a88d))
* use River comment syntax in Alloy config ([e0d7dd6](https://github.com/tomag-9/zdravy-projekt/commit/e0d7dd6cff5080063088f5788b99c8664252c5c6))


### Performance Improvements

* **admin:** optimize facility list queries ([a078fba](https://github.com/tomag-9/zdravy-projekt/commit/a078fba43a035256150b4758317761e8aadd26c8))
* cache admin celok list + gramage dashboard, stránkovanie /admin/facilities ([e817c42](https://github.com/tomag-9/zdravy-projekt/commit/e817c423f42a4cc66957ab8def6301de32966b20)), closes [#504](https://github.com/tomag-9/zdravy-projekt/issues/504)
* cache-async-celery ([#115](https://github.com/tomag-9/zdravy-projekt/issues/115)) ([3663c31](https://github.com/tomag-9/zdravy-projekt/commit/3663c31e53e277270f6c85d90541efac30cab57a))
* db queries & indexing ([#114](https://github.com/tomag-9/zdravy-projekt/issues/114)) ([18d9c23](https://github.com/tomag-9/zdravy-projekt/commit/18d9c2330dc82c55f50c7f4d886cc6bc24faa35c))


### Reverts

* **gramaz:** odstran 'hlavny udaj' blok, sumar uz len MS porcie ([#529](https://github.com/tomag-9/zdravy-projekt/issues/529)) ([6c812af](https://github.com/tomag-9/zdravy-projekt/commit/6c812aff556b99a84975b39e7f21f82030c802d5))
