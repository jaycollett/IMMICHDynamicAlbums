"""
Main application entry point for Immich Dynamic Albums.
"""
import argparse
import logging
import os
import sys
import time
from pathlib import Path

from immich_client import ImmichClient
from database import Database
from rules import RuleEngine, UserResolver, PeopleResolver


def setup_logging(log_level: str = "INFO"):
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def load_env_config() -> dict:
    """Load configuration from environment variables."""
    share_with_all = os.getenv("SHARE_WITH_ALL_USERS", "false").lower() in ("true", "1", "yes")

    # Parse SHARE_USER_IDS (comma-separated email list)
    share_user_emails_str = os.getenv("SHARE_USER_IDS", "")
    share_user_emails = [email.strip() for email in share_user_emails_str.split(",") if email.strip()]

    # Parse ALLOW_FUZZY_MATCH
    allow_fuzzy_match = os.getenv("ALLOW_FUZZY_MATCH", "false").lower() in ("true", "1", "yes")

    config = {
        "api_key": os.getenv("IMMICH_API_KEY"),
        "base_url": os.getenv("IMMICH_BASE_URL"),
        "sleep_interval": int(os.getenv("SLEEP_INTERVAL_SECONDS", "3600")),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "default_timezone": os.getenv("DEFAULT_TIMEZONE", "America/New_York"),
        "share_with_all_users": share_with_all,
        "share_user_emails": share_user_emails,
        "allow_fuzzy_match": allow_fuzzy_match,
    }

    # Validate required config
    if not config["api_key"]:
        raise ValueError("IMMICH_API_KEY environment variable is required")
    if not config["base_url"]:
        raise ValueError("IMMICH_BASE_URL environment variable is required")

    return config


def _rule_has_people_filter(rule: dict) -> bool:
    """Check if a rule (or recurring rule) has people filtering."""
    # Check filters format
    if "filters" in rule:
        filters = rule["filters"]
        if isinstance(filters, dict) and "people" in filters:
            return True

    # Check conditions format (recursively)
    if "conditions" in rule:
        return _condition_has_people(rule["conditions"])

    return False


def _condition_has_people(condition: any) -> bool:
    """Recursively check if a condition tree has people filters."""
    if isinstance(condition, dict):
        # Check for people filter
        if "people" in condition:
            return True

        # Check AND/OR branches
        if "and" in condition:
            return any(_condition_has_people(c) for c in condition["and"])
        if "or" in condition:
            return any(_condition_has_people(c) for c in condition["or"])

    elif isinstance(condition, list):
        return any(_condition_has_people(c) for c in condition)

    return False


def run_sync(
    client: ImmichClient,
    db: Database,
    rule_engine: RuleEngine,
    dry_run: bool = False,
    share_with_all_users: bool = False,
    share_user_emails: list = None,
    allow_fuzzy_match: bool = False
):
    """
    Run a single sync operation.

    Args:
        client: Immich API client
        db: Database connection
        rule_engine: Rule engine
        dry_run: If True, only log what would be done
        share_with_all_users: If True, share new albums with all users
        share_user_emails: List of email addresses to share albums with
        allow_fuzzy_match: If True, enable fuzzy matching globally (can be overridden per-rule)
    """
    logger = logging.getLogger(__name__)

    if dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN MODE - No changes will be made")
        logger.info("=" * 60)

    sync_run_id = db.start_sync_run()
    logger.info(f"Starting sync run #{sync_run_id}")

    # Build UserResolver if needed
    user_resolver = None
    global_share_user_ids = None

    needs_users = (
        share_with_all_users or
        (share_user_emails and len(share_user_emails) > 0) or
        rule_engine.has_per_rule_sharing()
    )

    if needs_users:
        try:
            all_users = client.get_all_users()
            logger.info(f"Fetched {len(all_users)} users from Immich")

            user_resolver = UserResolver(all_users)
            user_resolver.set_owner(client.get_my_user()["id"])

            # Resolve global sharing
            if share_with_all_users:
                global_share_user_ids = user_resolver.resolve_share_identifiers("ALL")
                if global_share_user_ids:
                    logger.info(f"Global sharing enabled: albums will be shared with {len(global_share_user_ids)} user(s)")
            elif share_user_emails:
                global_share_user_ids = user_resolver.resolve_share_identifiers(share_user_emails)
                if global_share_user_ids:
                    logger.info(f"Global sharing enabled: albums will be shared with {len(global_share_user_ids)} specific user(s)")
        except Exception as e:
            logger.warning(f"Failed to fetch users for sharing: {str(e)}")
            logger.warning("Continuing without album sharing")

    # Note: people_resolver is created before RuleEngine initialization in main()
    # and passed to RuleEngine constructor. RuleEngine stores it and uses it internally.

    try:
        # Pass None for people_resolver parameter (deprecated - RuleEngine uses self.people_resolver)
        stats = rule_engine.sync_all(
            client, db, dry_run,
            global_share_user_ids, user_resolver, None,
            allow_fuzzy_match
        )

        logger.info("=" * 60)
        logger.info("Sync completed")
        logger.info(f"Rules processed: {stats['rules_processed']}")
        logger.info(f"Assets added: {stats['total_assets_added']}")
        logger.info(f"Assets removed: {stats['total_assets_removed']}")

        if stats["errors"]:
            logger.warning(f"Errors encountered: {len(stats['errors'])}")
            for error in stats["errors"]:
                logger.warning(f"  - {error}")

        logger.info("=" * 60)

        # Record completion
        if not dry_run:
            status = "success" if not stats["errors"] else "partial"
            db.complete_sync_run(
                sync_run_id,
                status=status,
                rules_processed=stats["rules_processed"],
                assets_added=stats["total_assets_added"],
                assets_removed=stats["total_assets_removed"],
                error_message="; ".join(stats["errors"]) if stats["errors"] else None
            )

    except Exception as e:
        logger.error(f"Sync failed: {str(e)}", exc_info=True)
        if not dry_run:
            db.complete_sync_run(
                sync_run_id,
                status="error",
                error_message=str(e)
            )
        raise


def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(
        description="Immich Dynamic Albums - Automatically manage albums based on rules"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no changes will be made)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (don't loop)"
    )
    parser.add_argument(
        "--db-path",
        default="data/immich_albums.db",
        help="Path to SQLite database (default: data/immich_albums.db)"
    )

    args = parser.parse_args()

    # Load environment configuration
    env_config = load_env_config()
    setup_logging(env_config["log_level"])

    logger = logging.getLogger(__name__)
    logger.info("Immich Dynamic Albums starting...")

    # Ensure data directory exists
    db_dir = Path(args.db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    # Initialize components
    client = ImmichClient(env_config["base_url"], env_config["api_key"])
    db = Database(args.db_path)

    # Create PeopleResolver before RuleEngine (needed for condition tree building)
    # We need to do a preliminary check to see if any rules use people filtering
    # by loading the config first
    import yaml
    with open(args.config, 'r') as f:
        temp_config = yaml.safe_load(f)

    needs_people = any(
        _rule_has_people_filter(rule)
        for rule in temp_config.get("rules", [])
    )

    people_resolver = None
    if needs_people:
        try:
            all_people = client.get_all_people()
            logger.info(f"Fetched {len(all_people)} people from Immich for rule filtering")
            people_resolver = PeopleResolver(all_people)
        except Exception as e:
            logger.error(f"Failed to fetch people for filtering: {str(e)}")
            logger.error("This is required for rules with people filters")
            raise

    rule_engine = RuleEngine(
        args.config,
        default_timezone=env_config["default_timezone"],
        people_resolver=people_resolver
    )

    try:
        if args.once:
            # Run once and exit
            run_sync(
                client, db, rule_engine,
                args.dry_run,
                env_config["share_with_all_users"],
                env_config["share_user_emails"],
                env_config["allow_fuzzy_match"]
            )
        else:
            # Continuous loop
            logger.info(f"Running in continuous mode (sleep interval: {env_config['sleep_interval']}s)")
            while True:
                try:
                    run_sync(
                        client, db, rule_engine,
                        args.dry_run,
                        env_config["share_with_all_users"],
                        env_config["share_user_emails"],
                        env_config["allow_fuzzy_match"]
                    )
                except Exception as e:
                    logger.error(f"Error during sync: {str(e)}", exc_info=True)

                logger.info(f"Sleeping for {env_config['sleep_interval']} seconds...")
                time.sleep(env_config["sleep_interval"])

    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    finally:
        db.close()
        logger.info("Goodbye!")


if __name__ == "__main__":
    main()
