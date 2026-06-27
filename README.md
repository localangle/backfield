# Backfield

Backfield is a platform for turning unstructured news articles into structured, reusable editorial data.

## Key components

### Agate

Agate allows users to build workflows that extract arbitrary data from articles and enrich them with useful metadata. It also comes packaged with a robust human review interface, which editors can use to refine and correct the results.

### Stylebook

Stylebook serves as a canonical store of people, places and organizations that appear across an organization's coverage. It helps standardize entities into trustworthy objects that can be further enriched with metadata and connected to each other.

### Chronicle

*Coming soon.*

## Quick start

You need [Docker and Docker Compose](https://docs.docker.com/compose/) and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:localangle/backfield.git
cd backfield
make bootstrap          # install Python tooling
uv run backfield init   # set up env, start the stack, migrate, and seed
```

`backfield init` walks you through first-run setup and, when it finishes, opens the app in your browser:

- Agate: [http://localhost:5173](http://localhost:5173)
- Stylebook: [http://localhost:5175](http://localhost:5175)

To manage the stack afterward, use `uv run backfield up | down | logs | ps | restart`.

## License

*TBD.*

## Support

Questions or issues? See [docs.backfield.news](https://docs.backfield.news) or open an issue in this repository.