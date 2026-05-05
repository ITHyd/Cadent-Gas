const ASSET_BASE_URL = (import.meta.env.VITE_ASSET_BASE_URL || "").replace(
  /\/$/,
  "",
);

const MANUFACTURER_NODE_ID = "alarm_manufacturer";

const manufacturerLogos = {
  Aico: ["Aico", "Aico.png"],
  Cavius: ["Cavius", "Cavius.png"],
  FireAngel: ["FireAngel", "FireAngel.png"],
  Firehawk: ["Firehawk", "Firehawk.png"],
  "Google Nest": ["Google Nest", "Google Nest.png"],
  Honeywell: ["Honeywell", "Honeywell.png"],
  Kidde: ["Kidde", "Kidde.png"],
  Netatmo: ["Netatmo", "Netatmo.png"],
  "X-Sense": ["X-Sense", "X-Sense.png"],
  "Other / Cannot see": ["Other", "Other.png"],
};

const modelImagesByNodeId = {
  aico_model: {
    Ei3030: ["Aico", "Ei3030.png"],
    Ei3018: ["Aico", "Ei3018.png"],
    Ei3028: ["Aico", "Ei3028.png"],
    "Ei207 / Ei208 Series": ["Aico", "Ei207-Ei208.png"],
    "Not sure / another Aico model": ["Aico", "Other.png"],
  },
  aico_series_model: {
    "Ei207 / Ei207D": ["Aico", "Ei207-Ei208.png"],
    "Ei208 / Ei208W": ["Aico", "Ei207-Ei208.png"],
    Ei208WRF: ["Aico", "Ei207-Ei208.png"],
    "Not sure / cannot read it": ["Aico", "Other.png"],
  },
  fa_model: {
    FA6813: ["FireAngel", "FA6813.png"],
    FA6829S: ["FireAngel", "FA6829S.png"],
    FA3313: ["FireAngel", "FA3313.png"],
    FA3322: ["FireAngel", "FA3322.png"],
    FA3328: ["FireAngel", "FA3328.png"],
    FA3820: ["FireAngel", "FA3820.png"],
    FA6812: ["FireAngel", "FA6812.png"],
    "SCB10-R": ["FireAngel", "SCB10-R.png"],
    FP1820W2: ["FireAngel", "FP1820W2.png"],
    "Not sure / another FireAngel model": ["FireAngel", "Other.png"],
  },
  fh_model: {
    CO5B: ["Firehawk", "CO5B.png"],
    CO7B: ["Firehawk", "CO7B.png"],
    CO7BD: ["Firehawk", "CO7BD.png"],
    "CO10-RF": ["Firehawk", "CO10-RF.png"],
    "CO7B-10Y": ["Firehawk", "CO7B-10Y.png"],
    "Not sure / another Firehawk model": ["Firehawk", "Other.png"],
  },
  kidde_model: {
    "2030-DCR": ["Kidde", "2030-DCR.png"],
    K5CO: ["Kidde", "K5CO.png"],
    K5DCO: ["Kidde", "K5DCO.png"],
    K7CO: ["Kidde", "K7CO.png"],
    K7DCO: ["Kidde", "K7DCO.png"],
    K10LLCO: ["Kidde", "K10LLCO.png"],
    K10LLDCO: ["Kidde", "K10LLDCO.png"],
    KCOSAC2: ["Kidde", "KCOSAC2.png"],
    K4MCO: ["Kidde", "K4MCO.png"],
    K10SCO: ["Kidde", "K10SCO.png"],
    "Not sure / another Kidde model": ["Kidde", "Other.png"],
  },
  xs_model: {
    "XC01-M": ["X-Sense", "XC01-M.png"],
    "XC04-WX": ["X-Sense", "XC04-WX.png"],
    "XC01-R": ["X-Sense", "XC01-R.png"],
    "XC0C-SR": ["X-Sense", "XC0C-SR.png"],
    "XC0C-IR": ["X-Sense", "XC0C-iR.png"],
    "SC07-WX": ["X-Sense", "SC07-WX.png"],
    SC07: ["X-Sense", "SC07.png"],
    "SC07-W": ["X-Sense", "SC07-W.png"],
    "Not sure / another X-Sense model": ["X-Sense", "Other.png"],
  },
  hw_model: {
    XC70: ["Honeywell", "XC70.png"],
    XC100: ["Honeywell", "XC100.png"],
    XC100D: ["Honeywell", "XC100D.png"],
    "Not sure / another Honeywell model": ["Honeywell", "Other.png"],
  },
  nest_model: {
    "Nest Protect": ["Google Nest", "Nest-Protect.png"],
    "Not sure / another Nest alarm": ["Google Nest", "Other.png"],
  },
  net_model: {
    "Netatmo Smart CO Alarm": ["Netatmo", "Netatmo-Smart-CO-Alarm.png"],
    "Not sure / another Netatmo alarm": ["Netatmo", "Other.png"],
  },
  cav_model: {
    CV4002: ["Cavius", "CV4002.png"],
    "Not sure / another Cavius model": ["Cavius", "Other.png"],
  },
};

const buildAssetUrl = (segments) => {
  const encodedPath = segments.map((segment) => encodeURIComponent(segment)).join("/");
  const relativePath = `/images/manufacturers/${encodedPath}`;
  return ASSET_BASE_URL ? `${ASSET_BASE_URL}${relativePath}` : relativePath;
};

export const getWorkflowOptionVisual = (messageData, optionValue) => {
  const label =
    typeof optionValue === "object" && optionValue !== null && optionValue.label
      ? optionValue.label
      : optionValue;

  if (!label || !messageData?.node_id) {
    return null;
  }

  if (messageData.node_id === MANUFACTURER_NODE_ID) {
    const logo = manufacturerLogos[label];
    if (!logo) {
      return null;
    }
    return {
      label,
      imageUrl: buildAssetUrl(logo),
      kind: "manufacturer",
    };
  }

  const imageDef = modelImagesByNodeId[messageData.node_id]?.[label];
  if (!imageDef) {
    return null;
  }

  return {
    label,
    imageUrl: buildAssetUrl(imageDef),
    kind: "model",
  };
};

export const hasWorkflowOptionVisuals = (messageData, options) =>
  Array.isArray(options) &&
  options.some((option) => getWorkflowOptionVisual(messageData, option));
