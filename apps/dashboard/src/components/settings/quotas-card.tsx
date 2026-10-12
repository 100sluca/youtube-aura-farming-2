/**
 * Réglages → Quotas (docs/49 §9) : comment marchent les quotas des modèles, et pour chaque liste de clés la limite par jour
 * constatée (lue dans les refus de Google), la consommation du jour et la capacité de toutes les clés. Les chiffres
 * viennent du suivi des clés (migration 0044, worker/keyusage.py) : un modèle jamais appelé aujourd'hui n'apparaît pas.
 */
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { POOL_LABEL, frenchHour as hour, type KeyBoard } from "@/lib/api-key-types";

export function QuotasCard({ board }: { board: KeyBoard }) {
  return (
    <Card id="quotas">
      <CardHeader>
        <CardTitle>Quotas des modèles</CardTitle>
        <CardDescription>
          Les offres gratuites de Google limitent chaque clé, modèle par modèle : un nombre d’appels par minute et un nombre par jour. Le compteur du jour repart à minuit
          heure de Los Angeles, soit vers {board.resetAt ? hour(board.resetAt) : "9 h"} à Paris.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <ul className="text-muted-foreground flex list-disc flex-col gap-1 pl-5 text-xs leading-relaxed">
          <li>
            <strong className="text-foreground">Plusieurs clés</strong> : quand une clé atteint sa limite, l’appel passe aussitôt à la suivante ; une clé épuisée pour la journée
            n’est plus essayée jusqu’à minuit (Los Angeles). Chaque clé qui tombe fait une alerte.
          </li>
          <li>
            <strong className="text-foreground">Voix Gemini</strong> (drames) : les clés de la voix d’abord, puis celles de Réglages → IA ; toutes épuisées, la voix locale de repli
            (« Références émues ») prend le relais et une alerte le signale.
          </li>
          <li>
            <strong className="text-foreground">Modèles de langue</strong> (conteur, relecteur, idées, SEO…) : toutes les clés d’un modèle épuisées, la chaîne passe au modèle
            suivant (Réglages → IA).
          </li>
          <li>
            <strong className="text-foreground">Ailleurs</strong> : YouTube Data API, 10 000 unités par jour et 100 envois (carte ci-dessous) ; Gemini en ligne (clips), environ
            8 clips d’affilée puis quelques heures d’attente.
          </li>
        </ul>

        {board.groups.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-muted-foreground text-left">
                <tr className="border-b">
                  <th className="py-1.5 pr-3 font-medium">Modèle</th>
                  <th className="py-1.5 pr-3 font-medium">Clés</th>
                  <th className="py-1.5 pr-3 font-medium">Limite par clé et par jour</th>
                  <th className="py-1.5 pr-3 font-medium">Réussis aujourd’hui</th>
                  <th className="py-1.5 font-medium">Encore possibles</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {board.groups.map((g) => {
                  const capacity = g.limit ? g.limit * g.slots.length : null;
                  return (
                    <tr key={`${g.pool}-${g.model}`} className="border-b last:border-0">
                      <td className="py-1.5 pr-3">
                        <span className="text-muted-foreground">{POOL_LABEL[g.pool]} · </span>
                        {g.model}
                      </td>
                      <td className="py-1.5 pr-3">
                        {g.slots.length}
                        {g.down ? <span className="text-destructive"> ({g.down} tombée{g.down > 1 ? "s" : ""})</span> : null}
                      </td>
                      <td className="py-1.5 pr-3">{g.limit ?? <span className="text-muted-foreground">pas encore atteinte</span>}</td>
                      <td className="py-1.5 pr-3">{g.okToday}</td>
                      <td className="py-1.5">{capacity !== null ? `≈ ${Math.max(0, capacity - g.okToday)} sur ${capacity}` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-muted-foreground text-xs">Aucun appel relevé aujourd’hui : les chiffres apparaissent au premier appel (migration 0044 appliquée).</p>
        )}
        <p className="text-muted-foreground text-[11px]">
          La limite par jour est celle que Google annonce dans son premier refus (« limit: 10 requests per day ») : tant qu’aucune clé ne l’a atteinte, elle reste inconnue.
        </p>
      </CardContent>
    </Card>
  );
}
