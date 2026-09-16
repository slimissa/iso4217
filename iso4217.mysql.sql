-- ISO 4217 Currency Registry — SQL Export (MySQL 8+ / MariaDB 10.4+)
-- Source:      iso4217.json v1.5.2
-- Updated:     2026-09-16
-- Amendment:   179
-- Repository:  https://github.com/slimissa/iso4217
-- License:     Apache 2.0
--
-- Contents:    167 active + 135 withdrawn = 302 rows
--
-- Note:        Active codes are 3 chars (e.g., USD). Withdrawn codes
--              may be up to 7 chars (e.g., MXN_OLD) for revaluation cases.
-- Excludes:    non-ISO instruments (crypto, stablecoins, commodities),
--              peg information, country relationships, central banks
--
-- Regenerate:  python3 tools/export_sql.py
--

DROP TABLE IF EXISTS currencies;

CREATE TABLE currencies (
  code          VARCHAR(7)       NOT NULL,
  numeric_code  CHAR(3)          NOT NULL,
  name          VARCHAR(100)     NOT NULL,
  minor_units   TINYINT UNSIGNED NOT NULL,
  symbol        VARCHAR(20)      NULL,
  entity        VARCHAR(100)     NULL,
  status        VARCHAR(10)      NOT NULL,
  PRIMARY KEY (code),
  CONSTRAINT chk_currencies_code_length CHECK (LENGTH(code) BETWEEN 3 AND 7),
  CONSTRAINT chk_currencies_minor_units CHECK (minor_units BETWEEN 0 AND 18),
  CONSTRAINT chk_currencies_status CHECK (status IN ('active', 'withdrawn'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_currencies_status ON currencies (status);

-- Data

INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AED', '784', 'UAE Dirham', 2, 'د.إ', 'United Arab Emirates', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AFN', '971', 'Afghan Afghani', 2, '؋', 'Afghanistan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ALL', '008', 'Albanian Lek', 2, 'L', 'Albania', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AMD', '051', 'Armenian Dram', 2, '֏', 'Armenia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ANG', '532', 'Netherlands Antillean Guilder', 2, 'ƒ', 'Curaçao and Sint Maarten', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AOA', '973', 'Angolan Kwanza', 2, 'Kz', 'Angola', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ARS', '032', 'Argentine Peso', 2, '$', 'Argentina', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AUD', '036', 'Australian Dollar', 2, '$', 'Australia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AWG', '533', 'Aruban Florin', 2, 'Afl', 'Aruba', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AZN', '944', 'Azerbaijani Manat', 2, '₼', 'Azerbaijan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BAM', '977', 'Bosnia and Herzegovina Convertible Mark', 2, 'KM', 'Bosnia and Herzegovina', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BBD', '052', 'Barbadian Dollar', 2, 'Bds$', 'Barbados', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BDT', '050', 'Bangladeshi Taka', 2, '৳', 'Bangladesh', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BGN', '975', 'Bulgarian Lev', 2, 'лв', 'Bulgaria', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BHD', '048', 'Bahraini Dinar', 3, 'ب.د', 'Bahrain', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BIF', '108', 'Burundian Franc', 0, 'FBu', 'Burundi', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BMD', '060', 'Bermudian Dollar', 2, 'BD$', 'Bermuda', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BND', '096', 'Brunei Dollar', 2, 'B$', 'Brunei Darussalam', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BOB', '068', 'Bolivian Boliviano', 2, 'Bs', 'Bolivia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BOV', '984', 'Bolivian Mvdol', 2, 'BOV', 'Bolivia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BRL', '986', 'Brazilian Real', 2, 'R$', 'Brazil', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BSD', '044', 'Bahamian Dollar', 2, 'B$', 'Bahamas', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BTN', '064', 'Bhutanese Ngultrum', 2, 'Nu.', 'Bhutan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BWP', '072', 'Botswana Pula', 2, 'P', 'Botswana', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BYN', '933', 'Belarusian Ruble', 2, 'Br', 'Belarus', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BZD', '084', 'Belize Dollar', 2, 'BZ$', 'Belize', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CAD', '124', 'Canadian Dollar', 2, '$', 'Canada', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CDF', '976', 'Congolese Franc', 2, 'FC', 'Democratic Republic of the Congo', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CHE', '947', 'WIR Euro', 2, 'CHE', 'Switzerland', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CHF', '756', 'Swiss Franc', 2, 'CHF', 'Switzerland', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CHW', '948', 'WIR Franc', 2, 'CHW', 'Switzerland', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CLF', '990', 'Unidad de Fomento', 4, 'CLF', 'Chile', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CLP', '152', 'Chilean Peso', 0, '$', 'Chile', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CNY', '156', 'Chinese Yuan', 2, '¥', 'China', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('COP', '170', 'Colombian Peso', 2, '$', 'Colombia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('COU', '970', 'Unidad de Valor Real', 2, 'COU', 'Colombia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CRC', '188', 'Costa Rican Colon', 2, '₡', 'Costa Rica', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CUC', '931', 'Cuban Convertible Peso', 2, 'CUC$', 'Cuba', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CUP', '192', 'Cuban Peso', 2, '$MN', 'Cuba', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CVE', '132', 'Cape Verdean Escudo', 2, 'Esc', 'Cape Verde', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CZK', '203', 'Czech Koruna', 2, 'Kč', 'Czech Republic', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('DJF', '262', 'Djiboutian Franc', 0, 'Fdj', 'Djibouti', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('DKK', '208', 'Danish Krone', 2, 'kr', 'Denmark', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('DOP', '214', 'Dominican Peso', 2, 'RD$', 'Dominican Republic', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('DZD', '012', 'Algerian Dinar', 2, 'د.ج', 'Algeria', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('EGP', '818', 'Egyptian Pound', 2, 'E£', 'Egypt', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ERN', '232', 'Eritrean Nakfa', 2, 'Nfk', 'Eritrea', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ETB', '230', 'Ethiopian Birr', 2, 'Br', 'Ethiopia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('EUR', '978', 'Euro', 2, '€', 'European Union (Eurosystem)', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('FJD', '242', 'Fijian Dollar', 2, 'FJ$', 'Fiji', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('FKP', '238', 'Falkland Islands Pound', 2, 'FK£', 'Falkland Islands', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GBP', '826', 'Pound Sterling', 2, '£', 'United Kingdom', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GEL', '981', 'Georgian Lari', 2, '₾', 'Georgia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GHS', '936', 'Ghanaian Cedi', 2, 'GH₵', 'Ghana', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GIP', '292', 'Gibraltar Pound', 2, '£', 'Gibraltar', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GMD', '270', 'Gambian Dalasi', 2, 'D', 'Gambia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GNF', '324', 'Guinean Franc', 0, 'FG', 'Guinea', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GTQ', '320', 'Guatemalan Quetzal', 2, 'Q', 'Guatemala', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GYD', '328', 'Guyanese Dollar', 2, 'G$', 'Guyana', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('HKD', '344', 'Hong Kong Dollar', 2, 'HK$', 'Hong Kong SAR', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('HNL', '340', 'Honduran Lempira', 2, 'L', 'Honduras', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('HTG', '332', 'Haitian Gourde', 2, 'G', 'Haiti', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('HUF', '348', 'Hungarian Forint', 2, 'Ft', 'Hungary', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('IDR', '360', 'Indonesian Rupiah', 2, 'Rp', 'Indonesia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ILS', '376', 'Israeli New Shekel', 2, '₪', 'Israel', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('INR', '356', 'Indian Rupee', 2, '₹', 'India', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('IQD', '368', 'Iraqi Dinar', 3, 'ع.د', 'Iraq', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('IRR', '364', 'Iranian Rial', 2, '﷼', 'Iran', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ISK', '352', 'Icelandic Krona', 0, 'kr', 'Iceland', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('JMD', '388', 'Jamaican Dollar', 2, 'J$', 'Jamaica', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('JOD', '400', 'Jordanian Dinar', 3, 'د.ا', 'Jordan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('JPY', '392', 'Japanese Yen', 0, '¥', 'Japan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('KES', '404', 'Kenyan Shilling', 2, 'KSh', 'Kenya', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('KGS', '417', 'Kyrgyzstani Som', 2, 'с', 'Kyrgyzstan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('KHR', '116', 'Cambodian Riel', 2, '៛', 'Cambodia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('KMF', '174', 'Comorian Franc', 0, 'CF', 'Comoros', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('KPW', '408', 'North Korean Won', 2, '₩', 'North Korea', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('KRW', '410', 'South Korean Won', 0, '₩', 'South Korea', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('KWD', '414', 'Kuwaiti Dinar', 3, 'د.ك', 'Kuwait', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('KYD', '136', 'Cayman Islands Dollar', 2, 'CI$', 'Cayman Islands', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('KZT', '398', 'Kazakhstani Tenge', 2, '₸', 'Kazakhstan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LAK', '418', 'Lao Kip', 2, '₭', 'Laos', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LBP', '422', 'Lebanese Pound', 2, 'ل.ل', 'Lebanon', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LKR', '144', 'Sri Lankan Rupee', 2, 'රු', 'Sri Lanka', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LRD', '430', 'Liberian Dollar', 2, 'L$', 'Liberia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LSL', '426', 'Lesotho Loti', 2, 'L', 'Lesotho', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LYD', '434', 'Libyan Dinar', 3, 'ل.د', 'Libya', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MAD', '504', 'Moroccan Dirham', 2, 'د.م.', 'Morocco', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MDL', '498', 'Moldovan Leu', 2, 'L', 'Moldova', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MGA', '969', 'Malagasy Ariary', 2, 'Ar', 'Madagascar', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MKD', '807', 'Macedonian Denar', 2, 'ден', 'North Macedonia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MMK', '104', 'Myanmar Kyat', 2, 'K', 'Myanmar', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MNT', '496', 'Mongolian Tögrög', 2, '₮', 'Mongolia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MOP', '446', 'Macanese Pataca', 2, 'MOP$', 'Macao SAR', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MRU', '929', 'Mauritanian Ouguiya', 2, 'UM', 'Mauritania', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MUR', '480', 'Mauritian Rupee', 2, '₨', 'Mauritius', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MVR', '462', 'Maldivian Rufiyaa', 2, 'Rf', 'Maldives', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MWK', '454', 'Malawian Kwacha', 2, 'MK', 'Malawi', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MXN', '484', 'Mexican Peso', 2, '$', 'Mexico', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MXV', '979', 'Mexican Unidad de Inversion', 2, 'MXV', 'Mexico', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MYR', '458', 'Malaysian Ringgit', 2, 'RM', 'Malaysia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MZN', '943', 'Mozambican Metical', 2, 'MT', 'Mozambique', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('NAD', '516', 'Namibian Dollar', 2, 'N$', 'Namibia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('NGN', '566', 'Nigerian Naira', 2, '₦', 'Nigeria', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('NIO', '558', 'Nicaraguan Córdoba', 2, 'C$', 'Nicaragua', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('NOK', '578', 'Norwegian Krone', 2, 'kr', 'Norway', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('NPR', '524', 'Nepalese Rupee', 2, '₨', 'Nepal', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('NZD', '554', 'New Zealand Dollar', 2, '$', 'New Zealand', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('OMR', '512', 'Omani Rial', 3, 'ر.ع.', 'Oman', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PAB', '590', 'Panamanian Balboa', 2, 'B/.', 'Panama', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PEN', '604', 'Peruvian Sol', 2, 'S/', 'Peru', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PGK', '598', 'Papua New Guinean Kina', 2, 'K', 'Papua New Guinea', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PHP', '608', 'Philippine Peso', 2, '₱', 'Philippines', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PKR', '586', 'Pakistani Rupee', 2, '₨', 'Pakistan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PLN', '985', 'Polish Zloty', 2, 'zł', 'Poland', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PYG', '600', 'Paraguayan Guaraní', 0, '₲', 'Paraguay', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('QAR', '634', 'Qatari Riyal', 2, 'ر.ق', 'Qatar', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('RON', '946', 'Romanian Leu', 2, 'lei', 'Romania', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('RSD', '941', 'Serbian Dinar', 2, 'дин', 'Serbia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('RUB', '643', 'Russian Ruble', 2, '₽', 'Russia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('RWF', '646', 'Rwandan Franc', 0, 'FRw', 'Rwanda', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SAR', '682', 'Saudi Riyal', 2, 'ر.س', 'Saudi Arabia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SBD', '090', 'Solomon Islands Dollar', 2, 'SI$', 'Solomon Islands', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SCR', '690', 'Seychellois Rupee', 2, '₨', 'Seychelles', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SDG', '938', 'Sudanese Pound', 2, 'ج.س', 'Sudan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SEK', '752', 'Swedish Krona', 2, 'kr', 'Sweden', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SGD', '702', 'Singapore Dollar', 2, 'S$', 'Singapore', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SHP', '654', 'Saint Helena Pound', 2, '£', 'Saint Helena, Ascension and Tristan da Cunha', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SLE', '925', 'Sierra Leonean Leone', 2, 'Le', 'Sierra Leone', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SOS', '706', 'Somali Shilling', 2, 'Sh.So.', 'Somalia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SRD', '968', 'Surinamese Dollar', 2, '$', 'Suriname', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SSP', '728', 'South Sudanese Pound', 2, 'SS£', 'South Sudan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('STN', '930', 'São Tomé and Príncipe Dobra', 2, 'Db', 'São Tomé and Príncipe', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SVC', '222', 'Salvadoran Colón', 2, '₡', 'El Salvador', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SYP', '760', 'Syrian Pound', 2, '£S', 'Syria', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SZL', '748', 'Swazi Lilangeni', 2, 'L', 'Eswatini', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('THB', '764', 'Thai Baht', 2, '฿', 'Thailand', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TJS', '972', 'Tajikistani Somoni', 2, 'SM', 'Tajikistan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TMT', '934', 'Turkmenistani Manat', 2, 'm', 'Turkmenistan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TND', '788', 'Tunisian Dinar', 3, 'د.ت', 'Tunisia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TOP', '776', 'Tongan Paʻanga', 2, 'T$', 'Tonga', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TRY', '949', 'Turkish Lira', 2, '₺', 'Turkey', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TTD', '780', 'Trinidad and Tobago Dollar', 2, 'TT$', 'Trinidad and Tobago', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TWD', '901', 'New Taiwan Dollar', 2, 'NT$', 'Taiwan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TZS', '834', 'Tanzanian Shilling', 2, 'TSh', 'Tanzania', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UAH', '980', 'Ukrainian Hryvnia', 2, '₴', 'Ukraine', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UGX', '800', 'Ugandan Shilling', 0, 'USh', 'Uganda', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('USD', '840', 'US Dollar', 2, '$', 'United States', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('USN', '997', 'US Dollar (next day)', 2, 'USN', 'United States', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('USS', '998', 'US Dollar (same day)', 2, 'USS', 'United States', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UYI', '940', 'Uruguay Peso en Unidades Indexadas', 0, 'UYI', 'Uruguay', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UYU', '858', 'Uruguayan Peso', 2, '$U', 'Uruguay', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UYW', '927', 'Unidad Previsional', 4, 'UYW', 'Uruguay', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UZS', '860', 'Uzbekistani Som', 2, 'so''m', 'Uzbekistan', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('VED', '926', 'Venezuelan Digital Bolívar', 2, 'VED', 'Venezuela', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('VES', '928', 'Venezuelan Bolívar Soberano', 2, 'Bs.S', 'Venezuela', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('VND', '704', 'Vietnamese Dong', 0, '₫', 'Vietnam', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('VUV', '548', 'Vanuatu Vatu', 0, 'VT', 'Vanuatu', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('WST', '882', 'Samoan Tala', 2, 'WS$', 'Samoa', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('XAF', '950', 'Central African CFA Franc', 0, 'CFA', 'Economic and Monetary Community of Central Africa (CEMAC)', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('XCD', '951', 'East Caribbean Dollar', 2, 'EC$', 'Eastern Caribbean Currency Union', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('XOF', '952', 'West African CFA Franc', 0, 'CFA', 'West African Economic and Monetary Union (UEMOA)', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('XPF', '953', 'CFP Franc', 0, '₣', 'French Pacific Territories', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('YER', '886', 'Yemeni Rial', 2, '﷼', 'Yemen', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZAR', '710', 'South African Rand', 2, 'R', 'South Africa', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZMW', '967', 'Zambian Kwacha', 2, 'ZK', 'Zambia', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZWG', '924', 'Zimbabwe Gold', 2, 'ZiG', 'Zimbabwe', 'active');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ADF', '250', 'Andorran Franc', 2, 'F', 'France', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ADP', '020', 'Andorran Peseta', 0, 'Pts', 'Andorra', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AFA', '004', 'Afghan Afghani (old)', 2, '؋', 'Afghanistan', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ALK', '008', 'Albanian Lek (old)', 0, 'L', 'Albania', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AOK', '024', 'Angolan Kwanza (1977)', 0, 'Kz', 'Angola', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AON', '024', 'Angolan Novo Kwanza', 0, 'Kz', 'Angola', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AOR', '982', 'Angolan Kwanza Reajustado', 0, 'Kz', 'Angola', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ARA', '032', 'Argentine Austral', 2, '₳', 'Argentina', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ARL', '032', 'Argentine Peso Ley', 2, '$L', 'Argentina', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ARM', '032', 'Argentine Peso Moneda Nacional', 2, 'm$n', 'Argentina', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ARP', '032', 'Argentine Peso Argentino', 2, '$a', 'Argentina', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ARY', '032', 'Argentine Peso Ley (alternative code)', 0, '$L', 'Argentina', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ATS', '040', 'Austrian Schilling', 2, 'S', 'Austria', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('AZM', '031', 'Azerbaijani Manat (old)', 2, '₼', 'Azerbaijan', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BAD', '070', 'Bosnia and Herzegovina Dinar', 2, 'BAD', 'Bosnia and Herzegovina', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BEC', '993', 'Belgian Convertible Franc', 0, 'FB', 'Belgium', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BEF', '056', 'Belgian Franc', 2, 'fr.', 'Belgium', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BEL', '992', 'Belgian Financial Franc', 0, 'FB', 'Belgium', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BGJ', '100', 'Bulgarian Lev (1962)', 0, 'лв', 'Bulgaria', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BGK', '100', 'Bulgarian Lev (1997)', 0, 'лв', 'Bulgaria', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BGL', '100', 'Bulgarian Lev (1999)', 2, 'лв', 'Bulgaria', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BOP', '068', 'Bolivian Peso', 2, 'b$', 'Bolivia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BRB', '076', 'Brazilian Cruzeiro', 2, 'Cr$', 'Brazil', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BRC', '076', 'Brazilian Cruzado', 2, 'Cz$', 'Brazil', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BRE', '076', 'Brazilian Cruzeiro (1990)', 2, 'Cr$', 'Brazil', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BRN', '076', 'Brazilian Cruzado Novo', 2, 'NCz$', 'Brazil', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BRR', '987', 'Brazilian Cruzeiro Real', 2, 'CR$', 'Brazil', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BUK', '104', 'Burmese Kyat (old)', 0, 'K', 'Myanmar (formerly Burma)', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BYB', '112', 'Belarusian Ruble (1992)', 2, 'Br', 'Belarus', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('BYR', '974', 'Belarusian Ruble (2000)', 0, 'Br', 'Belarus', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CHC', '948', 'WIR Franc (electronic)', 2, 'CHC', 'Switzerland', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CSD', '891', 'Serbian Dinar (2003)', 2, 'CSD', 'Yugoslavia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CSJ', '203', 'Czechoslovak Koruna (1993)', 2, 'Kčs', 'Czechoslovakia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CSK', '200', 'Czechoslovak Koruna', 2, 'Kčs', 'Czechoslovakia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('CYP', '196', 'Cypriot Pound', 2, '£', 'Cyprus', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('DDM', '278', 'East German Mark', 0, 'M', 'German Democratic Republic', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('DEM', '276', 'German Mark', 2, 'DM', 'Germany', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ECS', '218', 'Ecuadorian Sucre', 0, 'S/.', 'Ecuador', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ECV', '983', 'Ecuadorian Unidad de Valor Constante', 2, 'UVC', 'Ecuador', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('EEK', '233', 'Estonian Kroon', 2, 'kr', 'Estonia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ESA', '996', 'Spanish Peseta (Account A)', 0, 'Pts', 'Spain', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ESB', '995', 'Spanish Peseta (Account B)', 0, 'Pts', 'Spain', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ESP', '724', 'Spanish Peseta', 0, 'Pts', 'Spain', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('FIM', '246', 'Finnish Markka', 2, 'mk', 'Finland', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('FRF', '250', 'French Franc', 2, 'F', 'France', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GEK', '268', 'Georgian Kuponi', 0, 'GEK', 'Georgia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GHC', '288', 'Ghanaian Cedi (old)', 2, 'GH₵', 'Ghana', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GHP', '939', 'Ghanaian Cedi (transitional)', 2, 'GH₵', 'Ghana', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GNE', '324', 'Guinean Syli', 0, 'S', 'Guinea', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GNS', '324', 'Guinean Syli (alternative code)', 0, 'S', 'Guinea', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GQE', '226', 'Equatorial Guinean Ekwele', 0, 'E', 'Equatorial Guinea', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GRD', '300', 'Greek Drachma', 0, 'Δρχ', 'Greece', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GWE', '624', 'Guinean Escudo', 0, 'GWE', 'Guinea-Bissau', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('GWP', '624', 'Guinea-Bissau Peso', 2, 'PG', 'Guinea-Bissau', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('HRD', '191', 'Croatian Dinar', 0, 'HRD', 'Croatia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('HRK', '191', 'Croatian Kuna', 2, 'kn', 'Croatia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('IEP', '372', 'Irish Pound', 2, '£', 'Ireland', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ILP', '376', 'Israeli Pound', 0, 'ILP', 'Israel', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ILR', '376', 'Israeli Shekel (old)', 2, 'IS', 'Israel', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ISJ', '352', 'Icelandic Króna (old)', 2, 'kr', 'Iceland', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ITL', '380', 'Italian Lira', 0, '₤', 'Italy', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LAJ', '418', 'Lao Kip (old)', 0, '₭', 'Laos', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LSM', '426', 'Lesotho Loti (old)', 0, 'L', 'Lesotho', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LTL', '440', 'Lithuanian Litas', 2, 'Lt', 'Lithuania', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LTT', '440', 'Lithuanian Talonas', 2, 'LTT', 'Lithuania', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LUC', '989', 'Luxembourg Convertible Franc', 0, 'LUC', 'Luxembourg', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LUF', '442', 'Luxembourg Franc', 2, 'F', 'Luxembourg', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LUL', '988', 'Luxembourg Financial Franc', 0, 'LUL', 'Luxembourg', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LVL', '428', 'Latvian Lats', 2, 'Ls', 'Latvia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('LVR', '428', 'Latvian Rublis', 2, 'LVR', 'Latvia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MCF', '250', 'Monégasque Franc', 2, 'F', 'France', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MGF', '450', 'Malagasy Franc', 0, 'FMG', 'Madagascar', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MKN', '807', 'Macedonian Denar (old)', 0, 'MKN', 'North Macedonia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MLF', '466', 'Malian Franc', 0, 'MLF', 'Mali', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MRO', '478', 'Mauritanian Ouguiya (old)', 2, 'UM', 'Mauritania', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MTL', '470', 'Maltese Lira', 2, 'Lm', 'Malta', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MTP', '470', 'Maltese Pound', 0, '£M', 'Malta', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MVQ', '462', 'Maldivian Rupee', 0, 'MRF', 'Maldives', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MXN_OLD', '484', 'Mexican Peso (pre-1993)', 2, 'MXP', 'Mexico', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MXP', '484', 'Mexican Peso (pre-1993)', 0, '$', 'Mexico', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MZE', '508', 'Mozambican Escudo', 2, 'MZE', 'Mozambique', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('MZM', '508', 'Mozambican Metical (old)', 2, 'MT', 'Mozambique', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('NIC', '558', 'Nicaraguan Córdoba (1988)', 2, 'C$', 'Nicaragua', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('NLG', '528', 'Dutch Guilder', 2, 'ƒ', 'Netherlands', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PEH', '604', 'Peruvian Sol de Oro', 0, 'S/.', 'Peru', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PEI', '604', 'Peruvian Inti', 0, 'I/.', 'Peru', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PES', '604', 'Peruvian Sol (alternative code)', 2, 'S/.', 'Peru', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PLZ', '616', 'Polish Zloty (old)', 2, 'PLZ', 'Poland', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('PTE', '620', 'Portuguese Escudo', 0, '$', 'Portugal', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('RHD', '716', 'Rhodesian Dollar', 2, 'R$', 'Zimbabwe', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ROK', '642', 'Romanian Leu (old)', 0, 'ROL', 'Romania', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ROL', '642', 'Romanian Leu (old)', 2, 'ROL', 'Romania', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('RUR', '810', 'Russian Ruble (old)', 2, 'RUR', 'Russia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SDD', '736', 'Sudanese Dinar', 2, 'SDD', 'Sudan', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SDP', '736', 'Sudanese Pound (old)', 0, 'SDP', 'Sudan', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SIT', '705', 'Slovenian Tolar', 2, 'SIT', 'Slovenia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SKK', '703', 'Slovak Koruna', 2, 'Sk', 'Slovakia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SLL', '694', 'Sierra Leonean Leone (old)', 2, 'Le', 'Sierra Leone', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SML', '380', 'San Marinese Lira', 0, '₤', 'Italy', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SRG', '740', 'Surinamese Guilder', 2, 'SRG', 'Suriname', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('STD', '678', 'São Tomé and Príncipe Dobra (old)', 2, 'Db', 'São Tomé and Príncipe', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('SUR', '810', 'Soviet Union Ruble', 0, 'SUR', 'Russia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TJR', '762', 'Tajikistani Ruble', 0, 'TJR', 'Tajikistan', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TMM', '795', 'Turkmenistani Manat (old)', 2, 'm', 'Turkmenistan', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TPE', '626', 'Portuguese Timorese Escudo', 0, '$', 'East Timor', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('TRL', '792', 'Turkish Lira (old)', 0, 'TL', 'Turkey', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UAK', '804', 'Ukrainian Karbovanets', 2, 'UAK', 'Ukraine', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UGS', '800', 'Ugandan Shilling (old)', 0, 'UGS', 'Uganda', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UGW', '800', 'Ugandan Shilling (old, alternative)', 0, 'UGW', 'Uganda', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UYN', '858', 'Uruguayan Peso (old)', 2, 'UYN', 'Uruguay', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('UYP', '858', 'Uruguayan New Peso', 0, 'UYP', 'Uruguay', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('VAL', '380', 'Vatican Lira', 0, '₤', 'Italy', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('VEB', '862', 'Venezuelan Bolívar (old)', 2, 'Bs', 'Venezuela', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('VEF', '937', 'Venezuelan Bolívar Fuerte', 2, 'Bs.F', 'Venezuela', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('VNC', '704', 'Vietnamese Dong (old)', 0, '₫', 'Vietnam', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('XEU', '954', 'European Currency Unit', 0, 'ECU', 'European Union', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('XFO', '955', 'Gold Franc', 0, 'XFO', 'Bank for International Settlements', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('XFU', '956', 'UIC Franc', 0, 'XFU', 'International Union of Railways', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('XRE', '957', 'RINET Funds Code', 0, 'XRE', 'RINET', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('YDD', '720', 'South Yemeni Dinar', 0, 'YD', 'Yemen (formerly South Yemen)', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('YUD', '890', 'Yugoslav Dinar (1966)', 2, 'din.', 'Yugoslavia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('YUG', '890', 'Yugoslav January Dinar', 2, 'din.', 'Yugoslavia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('YUM', '891', 'Yugoslav Novi Dinar', 2, 'din.', 'Yugoslavia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('YUN', '890', 'Yugoslav Convertible Dinar', 2, 'din.', 'Yugoslavia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('YUO', '890', 'Yugoslav October Dinar', 2, 'din.', 'Yugoslavia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('YUR', '890', 'Yugoslav Reformed Dinar', 2, 'din.', 'Yugoslavia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZAL', '991', 'South African Financial Rand', 2, 'ZAL', 'South Africa', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZMK', '894', 'Zambian Kwacha (1968)', 2, 'ZK', 'Zambia', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZRN', '180', 'Zairean New Zaire', 2, 'NZ', 'Democratic Republic of the Congo', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZRZ', '180', 'Zairean Zaire', 2, 'Z', 'Democratic Republic of the Congo', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZWC', '716', 'Rhodesian Dollar', 2, 'R$', 'Zimbabwe', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZWD', '716', 'Zimbabwean Dollar (1980)', 2, 'Z$', 'Zimbabwe', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZWL', '932', 'Zimbabwean Dollar (2009)', 2, 'Z$', 'Zimbabwe', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZWN', '942', 'Zimbabwean Dollar (2006)', 2, 'Z$', 'Zimbabwe', 'withdrawn');
INSERT INTO currencies (code, numeric_code, name, minor_units, symbol, entity, status) VALUES ('ZWR', '935', 'Zimbabwean Dollar (2008)', 2, 'Z$', 'Zimbabwe', 'withdrawn');

-- End of export
-- Active rows:    167
-- Withdrawn rows: 135
-- Total rows:     302
