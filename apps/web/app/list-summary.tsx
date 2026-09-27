import { Money } from "./components";

export function ListSummary({ title, description, cards }: { title: string; description: string;
  cards: { label: string; value: string | number; money?: boolean; hint: string }[] }) {
  return <section className="list-summary" aria-label={title}><h2>{title}</h2><p>{description}</p>
    <div className="support-metrics">{cards.map(card => <article className="metric" key={card.label}>
      <span>{card.label}</span><strong>{card.money ? <Money value={card.value} /> : Number(card.value).toLocaleString("en-IN")}</strong>
      <small>{card.hint}</small></article>)}</div></section>;
}
