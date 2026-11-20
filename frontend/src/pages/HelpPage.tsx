import { Link } from "react-router-dom";
import { Card, PageHeader } from "../components/ui/primitives";
import { StatusPill } from "../components/ui/status-pill";

function Step({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent">
        {number}
      </span>
      <div className="min-w-0">
        <h3 className="font-semibold text-ink">{title}</h3>
        <div className="mt-1 space-y-2 text-sm text-ink-muted">{children}</div>
      </div>
    </div>
  );
}

export default function HelpPage() {
  return (
    <>
      <PageHeader
        eyebrow="Supporto"
        title="Guida"
        description="Come configurare MdbUP da zero: provider, collezioni, snapshot, preview e liste MDBList."
        testId="help-header"
      />

      <div className="space-y-6" data-testid="help-page">
        <Card>
          <h2 className="text-lg font-semibold text-ink">Inizia qui</h2>
          <p className="mt-1 text-sm text-ink-muted">
            MdbUP non crea automaticamente provider, collezioni o liste: la configurazione
            iniziale è volutamente vuota. Le fonti (TMDb, JustWatch pubblico, ecc.) sono già
            registrate dal backend; provider e collezioni sono dati tuoi. Il comando
            <code> seed-providers</code> è solo un demo opzionale: non viene eseguito
            automaticamente e non va usato se vuoi partire da una configurazione pulita.
          </p>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Step number={1} title="Crea il primo admin">
              <p>
                Apri <Link className="text-accent underline" to="/bootstrap">/bootstrap</Link>,
                incolla il token di bootstrap e scegli una password di almeno 12 caratteri.
              </p>
            </Step>
            <Step number={2} title="Inserisci le credenziali">
              <p>
                Vai in <Link className="text-accent underline" to="/app/settings">Impostazioni → Credenziali</Link>.
                TMDb serve per i cataloghi TMDb; MDBList per le liste e le preview con confronto remoto.
              </p>
            </Step>
            <Step number={3} title="Crea un provider">
              <p>
                Apri <Link className="text-accent underline" to="/app/providers">Provider</Link> e usa
                <strong> Aggiungi provider</strong>. Scegli un servizio dall’elenco TMDb/JustWatch/TVDB
                (oppure inserisci gli ID manualmente). TVDB fornisce company ID e metadati, non la
                disponibilità per l’Italia; gli ID sono configurazione manuale: verificali sulla fonte
                prima di usarli.
              </p>
            </Step>
            <Step number={4} title="Crea una collezione">
              <p>
                Da <Link className="text-accent underline" to="/app/collections">Collezioni</Link> scegli
                provider, tipo media, fonte e tipo di collezione. Per JustWatch serve il package
                configurato sul provider; per TMDb servono gli ID del provider. La policy JustWatch
                si accetta quando crei il binding, non qui.
              </p>
            </Step>
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold text-ink">Provider e mapping</h2>
          <div className="mt-2 space-y-3 text-sm text-ink-muted">
            <p>
              Un <strong>provider</strong> è il servizio che vuoi monitorare (Netflix, Prime Video,
              un servizio locale, ecc.). MdbUP non ne installa nessuno: li crei tu.
            </p>
            <p>
              Un <strong>mapping</strong> collega il provider agli identificativi esterni:
              <span className="font-mono text-xs"> tmdb_movie_id</span>,
              <span className="font-mono text-xs"> tmdb_tv_id</span>,
              <span className="font-mono text-xs"> justwatch_short_name</span> e
              <span className="font-mono text-xs"> justwatch_technical_name</span>.
              Senza mapping la collezione viene rifiutata con <code>PROVIDER_NOT_VERIFIED</code>.
            </p>
            <div className="flex flex-wrap gap-2">
              <StatusPill label="Mapping verificato" tone="success" />
              <StatusPill label="Da verificare" tone="warning" />
              <StatusPill label="Nessun mapping" tone="neutral" />
            </div>
            <p>
              “Da verificare” non significa che il provider non esista: significa che l’ID è stato
              inserito manualmente e non è stato confermato live. Le collezioni si possono creare
              comunque, ma il flag <code>provider_mapping_verified</code> resta <code>false</code>.
            </p>
            <p>
              Questa versione non ha un editor di mapping: gli ID salvati restano quelli digitati
              alla creazione e non c’è un percorso per riallineare i mapping dal pannello. Controlla
              gli ID sulla fonte prima di salvare.
            </p>
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold text-ink">Collezioni, snapshot e preview</h2>
          <ol className="mt-2 list-decimal space-y-2 pl-5 text-sm text-ink-muted">
            <li>
              Crea una <strong>collezione</strong> dalla pagina Collezioni: catalogo, novità,
              in arrivo, classifica o filtro locale.
            </li>
            <li>
              Apri la collezione e premi <strong>Acquisisci ora</strong>: viene creato uno
              <strong> snapshot</strong> con i titoli e gli ID esterni.
            </li>
            <li>
              Usa <strong>Preview</strong> per calcolare il piano senza scrivere su MDBList.
            </li>
            <li>
              Solo dopo la preview crea un <strong>binding</strong> verso una lista MDBList.
            </li>
          </ol>
          <p className="mt-3 text-sm text-ink-muted">
            Una preview non modifica mai la lista. Un dry-run reale richiede la credenziale
            MDBList e non scrive nulla.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold text-ink">JustWatch: regole speciali</h2>
          <div className="mt-2 space-y-2 text-sm text-ink-muted">
            <p>
              JustWatch è un <strong>aggregatore</strong>: non dichiara la data di aggiunta al
              provider. Per questo le collezioni JustWatch hanno <code>date_basis=UNKNOWN</code>.
            </p>
            <p>
              Un binding JustWatch nasce <strong>disabilitato</strong>. Snapshot e preview sono
              sempre disponibili; una sync MDBList reale richiede un <strong>dry-run completato
              con successo</strong> ed è sempre manuale. Lo scheduler non avvia sync MDBList
              automatiche per JustWatch.
            </p>
            <p>
              Classifiche e “In arrivo” sono etichette dell’aggregatore, non una Top 10 ufficiale
              del provider.
            </p>
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold text-ink">Binding e sincronizzazione</h2>
          <div className="mt-2 space-y-2 text-sm text-ink-muted">
            <p>
              Un binding collega una collezione a una lista MDBList. La modalità
              <code> MIRROR</code> può rimuovere elementi; <code>APPEND_ONLY</code> non rimuove.
              Le soglie bloccano piani troppo distruttivi.
            </p>
            <p>
              Usa <strong>Dry-run</strong> per vedere quante aggiunte/rimozioni sarebbero
              necessarie. Un run reale può richiedere approvazione, a seconda delle soglie e
              della policy del binding.
            </p>
            <p>
              La pagina <Link className="text-accent underline" to="/app/runs">Run</Link> mostra
              stato, operazioni, errori e riconciliazioni. Le liste MDBList non vengono mai
              cancellate o ricreate da MdbUP.
            </p>
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold text-ink">Problemi comuni</h2>
          <dl className="mt-2 space-y-3 text-sm">
            <div>
              <dt className="font-semibold text-ink">“Provider non verificato”</dt>
              <dd className="text-ink-muted">
                Il provider non ha un mapping per quel tipo media o per la fonte scelta. Inserisci
                gli ID alla creazione del provider: questa versione non permette di modificarli
                dopo.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">“Dry-run richiesto”</dt>
              <dd className="text-ink-muted">
                Il binding JustWatch non ha ancora un dry-run riuscito. Esegui il dry-run dalla
                pagina Binding, poi abilita il binding.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">“Nessuna lista” o “Target non trovato”</dt>
              <dd className="text-ink-muted">
                Verifica la credenziale MDBList e che il target sia stato creato o importato.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">Errore con codice richiesta</dt>
              <dd className="text-ink-muted">
                Apri i log del container <code>api</code> e cerca il codice nella riga
                <code> http_request</code>: contiene percorso e stato HTTP.
              </dd>
            </div>
          </dl>
        </Card>
      </div>
    </>
  );
}
