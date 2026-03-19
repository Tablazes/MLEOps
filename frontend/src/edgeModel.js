/**
 * Edge sentiment model — draait volledig offline op het apparaat.
 * Lichtgewicht keyword-scoring als alternatief voor de cloud API.
 * Leeruitkomst 4: edge deployment.
 */

const NEG = ["pijn","benauwd","bloeding","bewusteloos","misselijk","hoofdpijn",
             "koorts","hartaanval","niet ademen","ernstig","help","erg","slecht",
             "gevallen","stuipen","epilepsie","overdosis","vergiftiging"]
const POS = ["goed","prima","beter","rustig","kalm","dankjewel","geen pijn",
             "oké","ok","normaal","stabiel","begrepen","duidelijk"]

export function edgeSentiment(text) {
  const t = text.toLowerCase()
  const score = POS.filter(w => t.includes(w)).length
               - NEG.filter(w => t.includes(w)).length
  return {
    sentiment: score >= 0 ? "positief" : "negatief",
    confidence: Math.min(0.50 + Math.abs(score) * 0.08, 0.90),
    source: "edge",
  }
}
